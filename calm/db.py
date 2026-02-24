#!/usr/bin/env python3
#
# Copyright (c) 2022 Jon Turney
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

#
# package db
#

import logging
import os

import peewee

from . import package
from . import utils


# database instance
_db = None
# tests currently need to be able to adjust this default
_uploads_allowed_default = False


# Get or create the global database instance, and initialize tables
def get_db(args):
    global _db
    if _db is None:
        utils.makedirs(args.htdocs)
        dbfn = os.path.join(args.htdocs, 'calm.db')
        logging.debug("sqlite3 database %s" % (dbfn))
        _db = peewee.SqliteDatabase(dbfn, autoconnect=False)

        models = [HistoricPackageName, VaultRequest, MissingObsolete, AnnounceMsgid, Maintainer]

        # set the database for all models
        for model in models:
            model.initialize(_db)

        # create tables, if they don't exist
        with _db.connection_context():
            _db.create_tables(models)

    return _db


# Reset the global database instance
def reset_db():
    global _db
    if _db is not None:
        _db.close()
        _db = None


# Model definitions
class BaseModel(peewee.Model):
    class Meta:
        database = peewee.SqliteDatabase(None)  # Will be set dynamically

    @classmethod
    def initialize(cls, db):
        cls._meta.database = db


# table which tracks all the package names we have ever seen
class HistoricPackageName(BaseModel):
    name = peewee.TextField(primary_key=True)

    class Meta:
        table_name = 'historic_package_names'


# table for vault requests made via 'calm-tool vault'
class VaultRequest(BaseModel):
    request_by = peewee.TextField()
    srcpackage = peewee.TextField()
    vr = peewee.TextField()

    class Meta:
        table_name = 'vault_requests'
        primary_key = False


# table recording accumulated missing_obsoletes data for packages
class MissingObsolete(BaseModel):
    arch = peewee.TextField()
    name = peewee.TextField()
    replaces = peewee.TextField()

    class Meta:
        table_name = 'missing_obsolete'
        indexes = (
            (('name', 'arch'), True),  # Unique composite primary key
        )
        primary_key = peewee.CompositeKey('arch', 'name')


# table recording reply-to message ID for package announcements
class AnnounceMsgid(BaseModel):
    msgid = peewee.TextField()
    srcpackage = peewee.TextField(primary_key=True)

    class Meta:
        table_name = 'announce_msgid'


class Maintainer(BaseModel):
    name = peewee.TextField(primary_key=True)
    email = peewee.TextField(null=True)
    last_reminder = peewee.DateTimeField(null=True)
    last_seen = peewee.DateTimeField(null=True)
    is_trusted = peewee.BooleanField(default=False)
    uploads_allowed = peewee.BooleanField(default=False)

    class Meta:
        table_name = 'maintainers'


# connect to the database
def connect(args):

    return get_db(args)


#
# this tracks the set of all names we have ever had for packages, and returns
# ones which aren't in the set of names for current package
#
def update_package_names(args, packages):
    db = connect(args)
    current_names = set(packages.keys())

    with db.connection_context():
        # get all historic names
        historic_names = set(
            row.name for row in HistoricPackageName.select()
        )

        # add newly appearing names to current_names
        new_names = current_names - historic_names
        for n in new_names:
            HistoricPackageName.create(name=n)
            logging.debug("package '%s' name is added" % (n))

    # this is data isn't quite perfect for this purpose: it doesn't know about:
    # - names which the removed package provide:d
    # - other packages which might provide: the name of a removed package
    return (historic_names - current_names)


#
# vault requests made via 'calm-tool vault'
#
def vault_requests(args, m):
    db = connect(args)
    requests = {}

    with db.connection_context():
        # get all requests for this user
        for row in VaultRequest.select().where(VaultRequest.request_by == m):
            spkg = row.srcpackage
            if spkg not in requests:
                requests[spkg] = set()
            requests[spkg].add(row.vr)

        # remove all rows for this user
        VaultRequest.delete().where(VaultRequest.request_by == m).execute()

    return requests


# Add a vault request
def vault_request_add(args, p, v, m):
    db = connect(args)

    with db.connection_context():
        VaultRequest.create(srcpackage=p, vr=v, request_by=m)


#
# this accumulates missing_obsoletes data for packages, so we will remember it
# even after the obsoleted package has been removed
#
# N.B. missing_obsolete data only exists for historic, and should be only
# applied to, x86_64 packages
def update_missing_obsolete(args, packages):
    db = connect(args)
    data = {}

    with db.connection_context():
        # read ...
        for row in MissingObsolete.select():
            data[row.name] = set(row.replaces.split())

        # then update missing obsoletes data
        missing_obsolete = package.upgrade_oldstyle_obsoletes(
            packages, data.copy()
        )

        # write updated records
        for name, replaces in missing_obsolete.items():
            replaces_str = ' '.join(replaces)
            if name not in data:
                MissingObsolete.create(
                    name=name,
                    arch='x86_64',
                    replaces=replaces_str
                )
            else:
                (MissingObsolete.update(replaces=replaces_str)
                 .where((MissingObsolete.name == name) &
                        (MissingObsolete.arch == 'x86_64'))
                 .execute())

    return missing_obsolete


def announce_msgid_get(args, srcpackage):
    db = connect(args)

    with db.connection_context():
        try:
            row = AnnounceMsgid.get_by_id(srcpackage)
            return row.msgid
        except AnnounceMsgid.DoesNotExist:
            return None


def announce_msgid_set(args, srcpackage, msgid):
    db = connect(args)

    with db.connection_context():
        AnnounceMsgid.create(srcpackage=srcpackage, msgid=msgid)


def maintainer_info(args, mlist):
    db = connect(args)

    with db.connection_context():
        for m in mlist.values():
            if m.name == 'ORPHANED':
                continue

            mi = Maintainer.get_or_none(Maintainer.name == m.name)
            if mi:
                m.uploads_allowed = mi.uploads_allowed
            else:
                mi = Maintainer.create(name=m.name)
                mi.uploads_allowed = _uploads_allowed_default

            mi.email = ','.join(m.email)
            mi.last_reminder = m.reminder_time
            mi.last_seen = m.last_seen
            mi.is_trusted = m.is_trusted
            mi.save()

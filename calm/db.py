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
import sqlite3

from . import package
from . import utils


def connect(args):
    utils.makedirs(args.htdocs)
    dbfn = os.path.join(args.htdocs, 'calm.db')
    logging.debug("sqlite3 database %s" % (dbfn))

    conn = sqlite3.connect(dbfn, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute('''CREATE TABLE IF NOT EXISTS historic_package_names
                    (name TEXT NOT NULL PRIMARY KEY
                    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS vault_requests
                    (srcpackage TEXT NOT NULL,
                     vr TEXT NOT NULL,
                     request_by TEXT NOT NULL
                    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS missing_obsolete
                    (name TEXT NOT NULL,
                     arch TEXT NOT NULL,
                     replaces TEXT NOT NULL,
                     PRIMARY KEY (name, arch)
                    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS announce_msgid
                    (srcpackage TEXT NOT NULL PRIMARY KEY,
                     msgid TEXT NOT NULL
                    )''')

    # migrations
    cursor = conn.execute("SELECT * FROM vault_requests LIMIT 1")
    cols = [row[0] for row in cursor.description]
    if 'request_by' not in cols:
        cursor.execute("ALTER TABLE vault_requests ADD COLUMN request_by TEXT NOT NULL DEFAULT ''")

    conn.commit()

    return conn


#
# this tracks the set of all names we have ever had for packages, and returns
# ones which aren't in the set of names for current package
#
def update_package_names(args, packages):
    current_names = set(packages.keys())

    with connect(args) as conn:
        conn.row_factory = sqlite3.Row

        cur = conn.execute("SELECT name FROM historic_package_names")
        historic_names = set([row['name'] for row in cur.fetchall()])

        # add newly appearing names to current_names
        for n in (current_names - historic_names):
            conn.execute('INSERT INTO historic_package_names (name) VALUES (?)', (n,))
            logging.debug("package '%s' name is added" % (n))

    # this is data isn't quite perfect for this purpose: it doesn't know about:
    # - names which the removed package provide:d
    # - other packages which might provide: the name of a removed package
    return (historic_names - current_names)


#
# vault requests made via 'calm-tool vault'
#
def vault_requests(args, m):
    requests = {}

    with connect(args) as conn:
        conn.row_factory = sqlite3.Row

        cur = conn.execute("SELECT * FROM vault_requests WHERE request_by = ?", (m,))
        for row in cur.fetchall():
            spkg = row['srcpackage']
            if spkg not in requests:
                requests[spkg] = set()
            requests[spkg].add(row)
            requests[spkg].add(row['vr'])

        # remove all rows
        cur = conn.execute("DELETE FROM vault_requests WHERE request_by = ?", (m,))

    return requests


def vault_request_add(args, p, v, m):
    with connect(args) as conn:
        conn.execute('INSERT INTO vault_requests (srcpackage, vr, request_by) VALUES (?,?, ?)', (p, v, m))


#
# this accumulates missing_obsoletes data for packages, so we will remember it
# even after the obsoleted package has been removed
#
# N.B. missing_obsolete data only exists for historic, and should be only
# applied to, x86_64 packages
def update_missing_obsolete(args, packages):
    data = {}
    with connect(args) as conn:
        conn.row_factory = sqlite3.Row

        # read
        cur = conn.execute("SELECT name, replaces FROM missing_obsolete")
        for row in cur.fetchall():
            data[row['name']] = set(row['replaces'].split())

        # update missing obsoletes data
        missing_obsolete = package.upgrade_oldstyle_obsoletes(packages, data.copy())

        # update
        for n, r in missing_obsolete.items():
            if n not in data:
                conn.execute('INSERT INTO missing_obsolete (name, arch, replaces) VALUES (?, ? , ?)', (n, 'x8_64', ' '.join(r)))
            else:
                conn.execute('UPDATE missing_obsolete SET replaces = ? WHERE name = ? AND arch = ?', (' '.join(r), n, 'x86_64'))

    return missing_obsolete


def announce_msgid_get(args, srcpackage):
    msgid = None
    with connect(args) as conn:
        conn.row_factory = sqlite3.Row

        cur = conn.execute("SELECT msgid FROM announce_msgid WHERE srcpackage = ?", (srcpackage,))
        row = cur.fetchone()
        if row:
            msgid = row['msgid']

    return msgid


def announce_msgid_set(args, srcpackage, msgid):
    with connect(args) as conn:
        conn.execute('INSERT INTO announce_msgid (srcpackage, msgid) VALUES (?, ?)', (srcpackage, msgid))

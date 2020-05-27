#!/usr/bin/env python3
#
# Copyright (c) 2015 Jon Turney
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
# utilities for working with a maintainer list
#

#
# things we know about a maintainer:
#
# - their home directory
# - the list of packages they maintain (given by cygwin-pkg-list)
# - an email address (in HOME/!email (or !mail), as we don't want to publish
#   it, and want to allow the maintainer to change it)
# - the timestamp when 'ignoring' warnings were last emitted
#

# XXX: Rather than this implementing an object which reads cygwin-pkg-maint when
# constructed at specific places in the code, perhaps this needs to contain the
# list (and it's inversion) and accessors, and invalidate that stored list when
# cygwin-pkg-maint changes...

from collections import defaultdict
import itertools
import logging
import os
import re

from . import utils

#
#
#


class Maintainer(object):
    _homedirs = ''

    def __init__(self, name, email=None, pkgs=None):
        if email is None:
            email = []
        if pkgs is None:
            pkgs = []

        self.name = name
        self.email = email
        self.pkgs = pkgs

        # the mtime of this file records the timestamp
        reminder_file = os.path.join(self.homedir(), '!reminder-timestamp')
        if os.path.exists(reminder_file):
            self.reminder_time = os.path.getmtime(reminder_file)
        else:
            self.reminder_time = 0
        self.reminders_issued = False
        self.reminders_timestamp_checked = False

    def __repr__(self):
        return "maintainers.Maintainer('%s', %s, %s)" % (self.name, self.email, self.pkgs)

    def homedir(self):
        return os.path.join(Maintainer._homedirs, self.name)

    def _update_reminder_time(self):
        reminder_file = os.path.join(self.homedir(), '!reminder-timestamp')

        if self.reminders_issued:
            # if reminders were issued, update the timestamp
            logging.debug("updating reminder time for %s" % self.name)
            utils.touch(reminder_file)
        elif (not self.reminders_timestamp_checked) and (self.reminder_time != 0):
            # if we didn't need to check the reminder timestamp, it can be
            # reset
            logging.debug("resetting reminder time for %s" % self.name)
            try:
                os.remove(reminder_file)
            except FileNotFoundError:
                pass

    @staticmethod
    def _find(mlist, name):
        mlist.setdefault(name, Maintainer(name))
        return mlist[name]

    # add maintainers which have existing directories
    @classmethod
    def add_directories(self, mlist, homedirs):
        self._homedirs = homedirs

        for n in os.listdir(homedirs):
            if not os.path.isdir(os.path.join(homedirs, n)):
                continue

            m = Maintainer._find(mlist, n)

            for e in ['!email', '!mail']:
                email = os.path.join(homedirs, m.name, e)
                if os.path.isfile(email):
                    with open(email) as f:
                        for l in f:
                            # one address per line, ignore blank and comment lines
                            if l.startswith('#'):
                                continue
                            l = l.strip()
                            if l:
                                m.email.append(l)
            if not m.email:
                logging.error("no email address known for maintainer '%s'" % (m.name))

        return mlist

    # add maintainers from the package maintainers list, with the packages they
    # maintain
    @staticmethod
    def add_packages(mlist, pkglist, orphanMaint=None):
        with open(pkglist) as f:
            for (i, l) in enumerate(f):
                l = l.rstrip()

                # match lines of the form '<package> <maintainer(s)|status>'
                match = re.match(r'^(\S+)\s+(.+)$', l)
                if match:
                    pkg = match.group(1)
                    rest = match.group(2)

                    # does rest starts with a status in all caps?
                    status_match = re.match(r'^([A-Z]+)\b.*$', rest)
                    if status_match:
                        status = status_match.group(1)

                        # ignore packages marked as 'OBSOLETE'
                        if status == 'OBSOLETE':
                            continue

                        # orphaned packages get the default maintainer if we
                        # have one, otherwise they are assigned to 'ORPHANED'
                        elif status == 'ORPHANED':
                            if orphanMaint is not None:
                                m = orphanMaint
                            else:
                                m = status

                            # also add any previous maintainer(s) listed
                            prevm = re.match(r'^ORPHANED\s\((.*)\)', rest)
                            if prevm:
                                m = m + '/' + prevm.group(1)

                        else:
                            logging.error("unknown package status '%s' in line %s:%d: '%s'" % (status, pkglist, i, l))
                            continue
                    else:
                        m = rest

                    # joint maintainers are separated by '/'
                    for name in m.split('/'):
                        name = name.strip()

                        # is the maintainer name ascii?
                        #
                        # (despite containing spaces, think of these as an account
                        # name, rather than a display name)
                        try:
                            name.encode('ascii')
                        except UnicodeError:
                            logging.error("non-ascii maintainer name '%s' in line %s:%d, skipped" % (rest, pkglist, i))
                            continue

                        m = Maintainer._find(mlist, name)
                        m.pkgs.append(pkg)

                else:
                    logging.error("unrecognized line in %s:%d: '%s'" % (pkglist, i, l))

        return mlist

    # create maintainer list
    @staticmethod
    def read(args, orphanmaint=None):
        mlist = {}
        mlist = Maintainer.add_directories(mlist, args.homedir)
        mlist = Maintainer.add_packages(mlist, args.pkglist, orphanmaint)

        return mlist

    # invert to a per-package list of maintainers
    @staticmethod
    def invert(mlist):
        _pkgs = defaultdict(list)
        # for each maintainer
        for m in mlist.values():
            # for each package
            for p in m.pkgs:
                # add the maintainer name
                _pkgs[p].append(m.name)

        return _pkgs

    @staticmethod
    def update_reminder_times(mlist):
        for m in mlist.values():
            m._update_reminder_time()

    # a list of all packages
    @staticmethod
    def all_packages(mlist):
        return list(itertools.chain.from_iterable(mlist[m].pkgs for m in mlist))

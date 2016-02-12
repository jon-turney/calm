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
#

import itertools
import logging
import os
import re
import sys


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

    def __repr__(self):
        return "maintainers.Maintainer('%s', %s, %s)" % (self.name, self.email, self.pkgs)

    def homedir(self):
        return os.path.join(Maintainer._homedirs, self.name)

    @staticmethod
    def _find(mlist, name):
        mlist.setdefault(name, Maintainer(name))
        return mlist[name]

    # add maintainers which have existing directories
    @classmethod
    def add_directories(self, mlist, homedirs):
        self._homedirs = homedirs

        for n in os.listdir(homedirs):
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

        return mlist

    # add maintainers from the package maintainers list, with the packages they
    # maintain
    @staticmethod
    def add_packages(mlist,  pkglist, orphanMaint=None):
        with open(pkglist) as f:
            for (i, l) in enumerate(f):
                l = l.rstrip()

                # match lines of the form '<package> <maintainer(s)>'
                match = re.match(r'^(\S+)\s+(.+)$', l)
                if match:
                    pkg = match.group(1)
                    m = match.group(2)

                    # orphaned packages get the default maintainer if we have
                    # one, otherwise are assigned to 'ORPHANED'
                    if m.startswith('ORPHANED'):
                        if orphanMaint is not None:
                            m = orphanMaint
                        else:
                            m = 'ORPHANED'

                    # joint maintainers are separated by '/'
                    for name in m.split('/'):
                        m = Maintainer._find(mlist, name)
                        m.pkgs.append(pkg)

                else:
                    logging.error("unrecognized line in %s:%d: '%s'" % (pkglist, i, l))

        return mlist

    # create maintainer list
    @staticmethod
    def read(args):
        mlist = {}
        mlist = Maintainer.add_directories(mlist, args.homedir)
        mlist = Maintainer.add_packages(mlist, args.pkglist, args.orphanmaint)

        return mlist

    # a list of all packages
    @staticmethod
    def all_packages(mlist):
        return list(itertools.chain.from_iterable(mlist[m].pkgs for m in mlist))

#
# We must be able to use pathnames which contain any character in the maintainer
# name, read from the maintainer list file.
#
# So, this test is somewhat sloppy.  In theory the filesystem encoding might be
# some encoding which can represent the subset of the io encoding that
# maintainer names actually use.  In practice, use a utf-8 locale.
#

if sys.getfilesystemencoding() != sys.getdefaultencoding():
    print("IO encoding is '%s', filesystem encoding is '%s'" % (sys.getdefaultencoding(), sys.getfilesystemencoding()), file=sys.stderr)
    print('It is required that IO encoded strings are convertible to the filesystem encoding', file=sys.stderr)
    print("Please set the locale", file=sys.stderr)
    exit(1)

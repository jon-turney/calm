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

import logging
import os
import re


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
    def add_packages(mlist,  pkglist, orphanMaint):
        with open(pkglist) as f:
            for (i, l) in enumerate(f):
                l = l.rstrip()

                # match lines of the form '<package> <maintainer(s)>'
                match = re.match(r'^(\S+)\s+(.+)$', l)
                if match:
                    pkg = match.group(1)
                    m = match.group(2)

                    # orphaned packages get the default maintainer if we have
                    # one, otherwise are ignored
                    if m.startswith('ORPHANED'):
                        if orphanMaint is not None:
                            m = orphanMaint
                        else:
                            continue

                    # joint maintainers are separated by '/'
                    for name in m.split('/'):
                        m = Maintainer._find(mlist, name)
                        m.pkgs.append(pkg)

                else:
                    logging.error("unrecognized line in %s:%d: '%s'" % (pkglist, i, l))

        return mlist

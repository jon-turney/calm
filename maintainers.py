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

import os
import re
import logging

import common_constants

class Maintainer(object):
    _homedirs = ''
    _list = {}

    def __init__(self, name):
        self.name = name
        self.email = ''
        self.pkgs = []

    def homedir(self):
        return os.path.join(Maintainer._homedirs, self.name)

    def get(name):
        if not name in Maintainer._list:
            Maintainer._list[name] = Maintainer(name)

        return Maintainer._list[name]

    def keys():
        return Maintainer._list.keys()

# add maintainers which have existing directories
def add_maintainer_directories(dir=None):
    if dir is None:
        dir = common_constants.HOMEDIRS
    Maintainer._homedirs = dir

    for n in os.listdir(dir):
        m = Maintainer.get(n)

        for e in ['!email', '!mail'] :
            email = os.path.join(dir, e)
            if os.path.isfile(email):
                with open(email) as f:
                    m.email = f.read()
                    # XXX: one line per address, ignore blank and comment lines

# add maintainers from the package maintainers list, with the packages they
# maintain
def add_maintainer_packages(pkglist=None, orphanMaint=None):
    if pkglist is None:
        pkglist = common_constants.PKGMAINT

    with open(pkglist) as f:
        for (i, l) in enumerate(f):
            l = l.rstrip()

            # match lines of the form '<package> <maintainer(s)>'
            match = re.match(r'^(\S+)\s+(.+)$', l)
            if match:
                pkg = match.group(1)
                m0 = match.group(2)

                # orphaned packages get the default maintainer if we have
                # one, otherwise are ignored
                if m0.startswith('ORPHANED'):
                    if orphanMaint is not None:
                        m0 = orphanMaint
                    else:
                        continue

                # ensure any metacharacters in pkg are escaped
                pkg = re.escape(pkg)

                # joint maintainers are separated by '/'
                for name in m0.split('/'):
                    m = Maintainer.get(name)
                    m.pkgs.append(pkg)

            else:
                logging.error("unrecognized line in %s:%d: '%s'" % (pkglist, i, l))

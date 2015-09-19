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
# utilities for working with a package database
#

import os
import re
import logging
from collections import defaultdict

import hint
import common_constants

class Package(object):
    def __init__(self):
        self.path = ''
        self.tars = []
        self.hints = {}

def read_packages(rel_area, arch):
    packages = defaultdict(Package)

    releasedir = os.path.join(rel_area, arch)
    logging.info('Reading packages from %s' % releasedir)

    for (dirpath, subdirs, files) in os.walk(releasedir):
        relpath = os.path.relpath(dirpath, releasedir)

        tars = list(filter(lambda f: re.search(r'\.tar.*$', f), files))
        tars = list(map(lambda f: os.path.join(arch, relpath, f), tars))

        if 'setup.hint' in files:
            # the package name is always the directory name
            p = os.path.basename(dirpath)

            # check for duplicate package names at different paths
            if p in packages:
                logging.error("duplicate package name at paths %s and %s" %
                              (dirpath, packages[p].path))
                continue

            hints = hint.setup_hint_parse(os.path.join(dirpath, 'setup.hint'))
            if 'parse-errors' in hints:
                logging.warning('Errors parsing hints for package %s' % p)
                continue

            packages[p].hints = hints
            packages[p].tars = tars
            packages[p].path = dirpath

        elif (len(files) > 0) and (relpath.count(os.path.sep) > 1):
            logging.warning("No setup hint in %s but files %s" % (dirpath, str(files)))

    logging.info("%d packages read" % len(packages))

    return packages

# a sorting which forces packages which begin with '!' to be sorted first,
# packages which begin with '_" to be sorted last, and others to be sorted
# case-insensitively
def sort_key(k):
    k = k.lower()
    if k[0] == '!':
        k = chr(0) + k
    elif k[0] == '_':
        k = chr(255) + k
    return k

if __name__ == "__main__":
    for arch in common_constants.ARCHES:
        packages = read_packages(common_constants.FTP, arch)
        print("arch %s has %d packages" % (arch, len(packages)))

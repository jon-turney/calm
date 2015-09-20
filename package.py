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
import tarfile
from collections import defaultdict

import hint
import common_constants

class Package(object):
    def __init__(self):
        self.path = '' # path to package, relative to release area
        self.tars = {}
        self.hints = {}

def read_packages(rel_area, arch):
    packages = defaultdict(Package)

    releasedir = os.path.join(rel_area, arch)
    logging.info('reading packages from %s' % releasedir)

    for (dirpath, subdirs, files) in os.walk(releasedir):
        relpath = os.path.relpath(dirpath, releasedir)

        if 'setup.hint' in files:
            files.remove('setup.hint')
            # the package name is always the directory name
            p = os.path.basename(dirpath)

            # check for duplicate package names at different paths
            if p in packages:
                logging.error("duplicate package name at paths %s and %s" %
                              (dirpath, packages[p].path))
                continue

            # read setup.hints
            hints = hint.setup_hint_parse(os.path.join(dirpath, 'setup.hint'))
            if 'parse-errors' in hints:
                for l in hints['parse-errors']:
                    logging.error("package '%s': %s" % (p, l))
                logging.error("errors while parsing hints for package '%s'" % p)
                continue

            # read sha512.sum
            sha512 = {}
            if not 'sha512.sum' in files:
                logging.warning("missing sha512.sum for package '%s'" % p)
                continue
            else:
                files.remove('sha512.sum')

                with open(os.path.join(releasedir, relpath, 'sha512.sum')) as fo:
                    for l in fo:
                        match = re.match(r'^(\S+)\s+(?:\*|)(\S+)$', l)
                        if match:
                            sha512[match.group(2)] = match.group(1)
                        else:
                            logging.warning("bad line '%s' in sha512.sum for package '%s'" % (l, p))

            # discard obsolete md5.sum
            if 'md5.sum' in files:
                files.remove('md5.sum')

            # collect the attributes for each tar file
            tars = {}
            missing = False

            # tar filenames must match the P-V-R convention.  P must match the
            # package name, V can contain anything, for R we allow some some
            # strings other than simple number, but it's unclear that is a good
            # idea
            for f in list(filter(lambda f: re.search(r'^' + re.escape(p) + '-.+-([0-9.]|alpha|bzr|git|hg|P|rc)*(-src|)\.tar\.(xz|bz2|gz)$', f), files)):
                files.remove(f)

                tars[f] = {}
                tars[f]['size'] = os.path.getsize(os.path.join(releasedir, relpath, f))

                if f not in sha512:
                    logging.error("no sha512.sum line for file %s in package '%s'" % (f, p))
                    missing = True
                    break
                else:
                    tars[f]['sha512'] = sha512[f]

            if missing:
                continue

            # warn about unexpected files, including tarfiles which don't match
            # the package name or package-version-release naming conventions
            if files:
                logging.warning("unexpected files in %s: %s" % (relpath, ', '.join(files)))

            packages[p].hints = hints
            packages[p].tars = tars
            packages[p].path = relpath

        elif (len(files) > 0) and (relpath.count(os.path.sep) > 1):
            logging.warning("no setup.hint in %s but files: %s" % (dirpath, ', '.join(files)))

    logging.info("%d packages read" % len(packages))

    return packages

#
# utility to determine if a tar file is empty
#
def tarfile_is_empty(tf):
    # sometimes compressed empty files used rather than a compressed empty tar
    # archive
    if os.path.getsize(tf) <= 32:
        return True

    # parsing the tar archive just to determine if it contains at least one
    # archive member is relatively expensive, so we just assume it contains
    # something if it's over a certain size threshold
    if os.path.getsize(tf) > 1024:
        return False

    # if it's really a tar file, does it contain zero files?
    with tarfile.open(tf) as a:
        if any(a) == 0:
            return True

    return False

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

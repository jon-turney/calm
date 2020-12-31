#!/usr/bin/env python3
#
# Copyright (c) 2017 Jon Turney
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

import argparse
import hashlib
import re
import os
import sys
import tarfile

from . import common_constants

#
# look for archives which are duplicated between x86 and x86_64
# (these should probably be moved to noarch or src)
#

#
# helper function to compute sha512 for a particular file
# (block_size should be some multiple of sha512 block size which can be
# efficiently read)
#


def sha512_file(f, block_size=256 * 128):
    sha512 = hashlib.sha512()

    for chunk in iter(lambda: f.read(block_size), b''):
        sha512.update(chunk)

    return sha512.hexdigest()

#
#
#


class TarMemberInfo:
    def __init__(self, info, sha512):
        self.info = info
        self.sha512 = sha512


def read_tar(f):
    result = {}

    try:
        with tarfile.open(f) as t:
            for m in t:
                if m.isfile():
                    f = t.extractfile(m)
                    sha512 = sha512_file(f)
                else:
                    sha512 = None
                result[m.name] = TarMemberInfo(m, sha512)
    except tarfile.ReadError:
        # if we can't read the tar archive, we should never consider it to have
        # the same contents as another tar archive...
        result[f] = None

    return result

#
#
#


def compare_archives(f1, f2):
    # for speed, first check that archives are of the same size
    if os.path.getsize(f1) != os.path.getsize(f2):
        return 'different archive size'

    # if they are both compressed empty files (rather than compressed empty tar
    # archives), they are the same
    if os.path.getsize(f1) <= 32:
        return None

    t1 = read_tar(f1)
    t2 = read_tar(f2)

    if t1.keys() != t2.keys():
        return 'different member lists'

    for m in t1:
        # compare size of member
        if t1[m].info.size != t2[m].info.size:
            return 'different size for member %s' % m

        # compare type of member
        if t1[m].info.type != t2[m].info.type:
            return 'different type for member %s' % m

        # for files, compare hash of file content
        if t1[m].info.isfile():
            if t1[m].sha512 != t2[m].sha512:
                return 'different hash for member %s' % m
        # for links, compare target
        elif t1[m].info.islnk() or t1[m].info.issym():
            if t1[m].info.linkname != t2[m].info.linkname:
                return 'different linkname for member %s' % m

        # permitted differences: mtime, mode, owner uid/gid

    return None

#
#
#


def find_duplicates(args):
    basedir = os.path.join(args.rel_area, common_constants.ARCHES[0], 'release')

    for (dirpath, _subdirs, files) in os.walk(basedir):
        relpath = os.path.relpath(dirpath, basedir)
        otherdir = os.path.join(args.rel_area, common_constants.ARCHES[1], 'release', relpath)

        for f in files:
            # not an archive
            if not re.match(r'^.*\.tar' + common_constants.PACKAGE_COMPRESSIONS_RE + r'$', f):
                continue

            f1 = os.path.join(dirpath, f)
            f2 = os.path.join(otherdir, f)

            if os.path.exists(f2):
                difference = compare_archives(f1, f2)
                if difference is None:
                    print(os.path.join('release', relpath, f))
                elif args.verbose:
                    print('%s: %s' % (os.path.join('release', relpath, f), difference))

#
#
#


def main():
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='Source package deduplicator')
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output')
    (args) = parser.parse_args()

    return find_duplicates(args)


#
#
#

if __name__ == "__main__":
    sys.exit(main())

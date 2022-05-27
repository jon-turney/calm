#!/usr/bin/env python3
#
# Copyright (c) 2020 Jon Turney
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
import logging
import os
import re
import sys

from . import common_constants
from . import fixes


def fix_hints(relarea, packages, fixids):
    for (dirpath, _subdirs, files) in os.walk(relarea):

        # only apply to listed packages, if specified
        if packages:
            relpath = os.path.relpath(dirpath, relarea)
            relpath = relpath.split(os.path.sep)
            if (len(relpath) < 3) or (relpath[2] not in packages):
                continue

        for f in files:
            match = re.match(r'^(.*)-src\.tar' + common_constants.PACKAGE_COMPRESSIONS_RE + r'$', f)
            if match:
                hf = match.group(1) + '-src.hint'
                if hf not in files:
                    logging.error('hint %s missing' % hf)
                    continue

                fixes.fix_hint(dirpath, hf, f, fixids)


#
#
#

def main():
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='src hint improver')
    parser.add_argument('package', nargs='*', metavar='PACKAGE')
    parser.add_argument('--fix', action='append', help='ids of fixes to perform')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output', default=0)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='relarea')
    (args) = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    if not args.fix:
        args.fix = ['homepage', 'license']

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    fix_hints(args.relarea, args.package, args.fix)


#
#
#

if __name__ == "__main__":
    sys.exit(main())

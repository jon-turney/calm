#!/usr/bin/env python3
#
# Copyright (c) 2021 Jon Turney
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
import sys

from . import common_constants
from . import fixes


#
#
#

def fix_hints(relarea, packages):
    for (dirpath, _subdirs, files) in os.walk(relarea):

        # only apply to listed packages, if specified
        if packages:
            relpath = os.path.relpath(dirpath, relarea)
            relpath = relpath.split(os.path.sep)
            if (len(relpath) < 3) or (relpath[2] not in packages):
                continue

        for f in files:
            if f.endswith('.hint') and f != 'override.hint':
                if fixes.fix_hint(dirpath, f, '', ['invalid_keys']):
                    logging.warning('fixed hints %s' % f)


#
#
#

def main():
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='fix invalid keys in hint')

    parser.add_argument('package', nargs='*', metavar='PACKAGE')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output', default=0)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='relarea')
    # XXX: should take an argument listing fixes to apply

    (args) = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    fix_hints(args.relarea, args.package)


#
#
#

if __name__ == "__main__":
    sys.exit(main())

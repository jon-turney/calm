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
import shutil
import sys

from . import common_constants

#
#
#


def fix_hints(relarea):
    for (dirpath, _subdirs, files) in os.walk(relarea):
        for f in files:
            match = re.match(r'^(.*)-src\.tar\.(bz2|gz|lzma|xz)$', f)
            if match:
                pvr = match.group(1)
                old = pvr + '.hint'
                new = pvr + '-src.hint'
                if (old in files) and (new not in files):
                    logging.info("copying '%s' to '%s'" % (old, new))
                    shutil.copy2(os.path.join(dirpath, old), os.path.join(dirpath, new))
                    if f.replace('-src', '') not in files:
                        logging.info("removing '%s'" % (old))
                        os.rename(os.path.join(dirpath, old), os.path.join(dirpath, old + '.bak'))


#
#
#

def main():
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='src hint creator')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output', default=0)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='relarea')
    (args) = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    fix_hints(args.relarea)


#
#
#

if __name__ == "__main__":
    sys.exit(main())

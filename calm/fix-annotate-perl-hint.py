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

#
# Annotate existing hints with requires: perl with a comment noting these
# require perl5.26 (or possibly earlier), before we deploy perl5.30.  Later
# these comments can be transformed into an requires: on an additional provides:
# in perl_base package.
#

import argparse
import logging
import os
import re
import shutil
import sys

from . import common_constants
from . import hint

#
#
#


def fix_one_hint(dirpath, hintfile):
    pn = os.path.join(dirpath, hintfile)

    with open(pn, 'r') as f:
        for l in f:
            if 'perl5_26' in l:
                logging.info("%s already annotated" % (hintfile))
                return

    hints = hint.hint_file_parse(pn, hint.pvr)

    requires = hints.get('requires', '').split()
    if requires:
        if ('perl_base' in requires) or ('perl' in requires):
            logging.info("%s has perl in requires" % (hintfile))

            shutil.copy2(pn, pn + '.bak')
            with open(pn, 'a') as f:
                print("# perl5_26", file=f)


def fix_hints(relarea):
    for (dirpath, subdirs, files) in os.walk(relarea):
        for f in files:
            match = re.match(r'^.*\.hint$', f)
            if match:
                fix_one_hint(dirpath, f)

#
#
#


if __name__ == "__main__":
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='perl requires annotater')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output', default=0)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='relarea')
    (args) = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    fix_hints(args.relarea)

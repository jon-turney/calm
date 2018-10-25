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
import re
import os
import shutil
import sys

from . import common_constants
from . import hint

#
# migrate setup.hint to pvr.hint
#
# (just copy setup.hint to any missing pvr.hint. we don't need to bother
# cleaning up setup.hint which are no longer needed, as calm can do that)
#


def hint_migrate(args):
    for arch in common_constants.ARCHES + ['noarch']:
        basedir = os.path.join(args.rel_area, arch, 'release')

        for (dirpath, subdirs, files) in os.walk(basedir):

            if 'setup.hint' not in files:
                continue
            setup_hint_fn = os.path.join(dirpath, 'setup.hint')

            migrate = set()
            vr = set()
            for f in files:
                match = re.match(r'^(.*?)(-src|)\.tar\.(bz2|gz|lzma|xz)$', f)

                # not an archive?
                if not match:
                    continue

                pvr = match.group(1)
                vr.add(pvr)

                # pvr.hint already exists?
                if os.path.exists(os.path.join(dirpath, pvr + '.hint')):
                    continue

                migrate.add(pvr)

            # nothing to migrate
            if not migrate:
                # that's ok if all vr already have a pvr.hint, but if we didn't
                # find any vr, something is wrong
                if not vr:
                    print("can't migrate %s as it has no versions" % (setup_hint_fn))
                continue

            # does the setup.hint parse as a pvr.hint?
            hints = hint.hint_file_parse(setup_hint_fn, hint.pvr)
            if 'parse-errors' in hints:
                reason = "is invalid as a pvr.hint"

                # specifically mention if it doesn't parse as a pvr.hint because
                # it contains version keys
                for e in hints['parse-errors']:
                    if (e.startswith('unknown key prev') or
                        e.startswith('unknown key curr') or
                        e.startswith('test has non-empty value')):
                        reason = "contains version keys"

                print("can't migrate %s as it %s" % (setup_hint_fn, reason))
                continue

            for pvr in migrate:
                pvr_hint_fn = os.path.join(dirpath, pvr + '.hint')
                print('copy %s -> %s' % (setup_hint_fn, pvr_hint_fn))
                shutil.copy2(setup_hint_fn, pvr_hint_fn)


#
#
#

def main():
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='setup.hint migrator')
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    (args) = parser.parse_args()

    return hint_migrate(args)


#
#
#

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
#
# Copyright (c) 2023 Jon Turney
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
import tarfile

import xtarfile

from . import common_constants
from . import hint

#
#
#


def fix_one_hint(args, dirpath, hintfile, tf):
    pn = os.path.join(dirpath, hintfile)

    hints = hint.hint_file_parse(pn, hint.pvr)

    hints.pop('parse-warnings', None)
    if 'parse-errors' in hints:
        logging.error('invalid hints %s' % hintfile)
        return

    modified = False

    requires = hints.get('requires', '').split()
    if requires:
        # requires is already present?
        if args.requires in requires:
            return

    # check if this package installs any files with the specified path, and if
    # so, add to the requires, if not already present
    ivp = False

    try:
        with xtarfile.open(os.path.join(dirpath, tf), mode='r') as a:
            ivp = any((m.isfile() and re.match(args.path, m.name)) for m in a.getmembers())
    except tarfile.ReadError:
        pass

    if ivp:
        logging.info('found matching path in %s' % (tf))
        requires = hints.get('requires', '').split()
        if args.requires not in requires:
            if args.replace and args.replace in requires:
                requires.remove(args.replace)
            requires.append(args.requires)
            requires = sorted(requires)
            modified = True
            logging.warning("adding %s to requires in %s" % (args.requires, hintfile))
        hints['requires'] = ' '.join(requires)

    if not modified:
        return

    # write updated hints
    shutil.copy2(pn, pn + '.bak')
    hint.hint_file_write(pn, hints)
    if args.verbose:
        os.system('/usr/bin/diff -uBZ %s %s' % (pn + '.bak', pn))


def fix_hints(args):
    for (dirpath, _subdirs, files) in os.walk(args.relarea):
        for f in files:
            match = re.match(r'^([^-].*?)\.tar' + common_constants.PACKAGE_COMPRESSIONS_RE + r'$', f)
            if match:
                root = match.group(1)
                if root.endswith('-src'):
                    continue

                pn = root.rsplit('-', 2)[0]

                # is pn in the list of packages (if specified)?
                if args.package and (pn not in args.package):
                    continue

                # avoid pointlessly checking to add a self-dependency
                if pn == args.requires:
                    return

                logging.info('Checking %s' % root)

                fix_one_hint(args, dirpath, root + '.hint', f)

#
#
#


if __name__ == "__main__":
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='Add DEPATOM to requires: of packages which contain a file starting with PATH')
    parser.add_argument('path', metavar='PATH', help='regex of path to match')
    parser.add_argument('requires', metavar='DEPATOM', help='require to add')
    parser.add_argument('package', metavar='PACKAGE', action='extend', nargs='*', help='packages to check')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output', default=0)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='relarea')
    parser.add_argument('--replace', action='store', metavar='DEPATOM', help="replace existing DEPATOM if present")
    (args) = parser.parse_args()

    if not args.path.startswith('/'):
        sys.exit('must use an absolute path')
    else:
        args.path = args.path[1:]

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    fix_hints(args)

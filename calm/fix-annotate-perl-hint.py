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
import tarfile
import xtarfile

from . import common_constants
from . import hint

# packages which are known to embed a perl interpreter or contain perl extension
# dlls (i.e. link with libperl)
known_packages = [
    'perl-gdal',
    'hexchat-perl',
    'irssi',
    'postgresql-contrib',
    'postgresql-plperl',
    'rxvt-unicode',
    'weechat-perl',
    'znc-perl',
]

#
#
#


def fix_one_hint(dirpath, hintfile, tf):
    pn = os.path.join(dirpath, hintfile)

    hints = hint.hint_file_parse(pn, hint.pvr)

    hints.pop('parse-warnings', None)
    if 'parse-errors' in hints:
        logging.error('invalid hints %s' % hintfile)
        return

    modified = False

    # if no annotation yet, add a perl annotation
    if 'notes' not in hints:
        requires = hints.get('requires', '').split()
        if requires:
            if ('perl_base' in requires) or ('perl' in requires):
                logging.info("%s has perl in requires and no annotations" % (hintfile))
                hints['notes'] = 'perl5_030'
                modified = True

    # if annotated, check if this package installs into vendor_perl, and if so,
    # add the annotate perl version to requires, if not already present
    if hints.get('notes', '').startswith('perl5_0'):
        ivp = False
        exe = False

        try:
            with xtarfile.open(os.path.join(dirpath, tf), mode='r') as a:
                ivp = any(re.match(r'usr/(lib|share)/perl5/vendor_perl/', m) for m in a.getnames())
                exe = any(re.search(r'\.(exe|dll)$', m) for m in a.getnames())
        except tarfile.ReadError:
            pass

        knwn = any(hintfile.startswith(k) for k in known_packages)

        if ivp or knwn:
            requires = hints.get('requires', '').split()
            if hints['notes'] not in requires:
                requires.append(hints['notes'])
                requires = sorted(requires)
                modified = True
                logging.warning("adding perl provide to requires in %s" % (hintfile))
            hints['requires'] = ' '.join(requires)
        else:
            if exe:
                logging.info("%s has perl in requires, and might have content linked to libperl" % (hintfile))
            else:
                logging.info("%s has perl in requires, assuming that's for a perl script" % (hintfile))

    if not modified:
        return

    # write updated hints
    shutil.copy2(pn, pn + '.bak')
    hint.hint_file_write(pn, hints)
    # os.system('/usr/bin/diff -uBZ %s %s' % (pn + '.bak', pn))


def fix_hints(relarea):
    for (dirpath, _subdirs, files) in os.walk(relarea):
        for f in files:
            match = re.match(r'^([^-].*?)\.tar' + common_constants.PACKAGE_COMPRESSIONS_RE + r'$', f)
            if match:
                root = match.group(1)
                if root.endswith('-src'):
                    continue

                fix_one_hint(dirpath, root + '.hint', f)

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

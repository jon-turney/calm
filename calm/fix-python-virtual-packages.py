#!/usr/bin/env python3
#
# Copyright (c) 2026 Jon Turney
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
from . import hint

#
#
#


def python_virtual_migrate(args, dirpath, hintfile, modules):
    fn = os.path.join(dirpath, hintfile)
    hints = hint.hint_file_parse(fn, hint.pvr)

    hints.pop('parse-warnings', None)
    if 'parse-errors' in hints:
        logging.error('invalid hints %s' % hintfile)
        return

    modified = False

    # identify module name

    # strip '.hint'
    pn = hintfile[:-5]
    # strip optional arch
    pn = re.sub('-(' + '|'.join(['noarch'] + common_constants.ARCHES) + ')$', '', pn)
    # strip version
    pn = pn.rsplit('-', 2)[0]

    module_name = pn.replace('python3-', '')

    if 'Virtual' not in hints['category'].split():
        logging.debug('not virtual')
        return

    requires = hints.get('requires', '').split()
    if len(requires) != 1:
        logging.error('%s has confusing requires: %s' % (hintfile, requires))
        return

    if module_name not in modules:
        logging.error('Cannot update %s requires: as updated %s does not exist' % (hintfile, module_name))
        return

    # already correct
    updated = 'python' + args.pyversion + '-' + module_name
    if requires[0] == updated:
        logging.info('%s is already has correct requires:' % (hintfile))
        return

    if re.match(r'python\d+-' + module_name, requires[0]):
        requires[0] = updated
        hints['requires'] = ' '.join(requires)
        modified = True

    if not modified:
        return

    logging.error('%s modified' % (hintfile))

    # write updated hints
    shutil.copy2(fn, fn + '.bak')
    hint.hint_file_write(fn, hints)
    if args.verbose:
        os.system('/usr/bin/diff -uBZ %s %s' % (fn + '.bak', fn))


def scan_hints(args):
    modules = set()

    # first scan to build a list of python3XX-foo modules
    for (_dirpath, _subdirs, files) in os.walk(args.relarea):
        for f in files:
            if f.endswith('.hint') and f != 'override.hint' and not f.endswith('src.hint'):
                # strip '.hint'
                pn = f[:-5]
                # strip optional arch
                pn = re.sub('-(' + '|'.join(['noarch'] + common_constants.ARCHES) + ')$', '', pn)
                # strip version
                pn = pn.rsplit('-', 2)[0]

                prefix = 'python' + args.pyversion + '-'
                if pn.startswith(prefix):
                    module_name = pn.replace(prefix, '')
                    logging.info('Adding %s' % module_name)
                    modules.add(module_name)

    logging.error('python %s modules are: %s' % (args.pyversion, sorted(modules)))

    # then scan to update python3-foo modules
    for (dirpath, _subdirs, files) in os.walk(args.relarea):
        for f in files:
            if f.endswith('.hint') and f != 'override.hint' and not f.endswith('src.hint'):
                if not f.startswith('python3-'):
                    continue

                logging.info('Checking %s' % f)
                python_virtual_migrate(args, dirpath, f, modules)

#
#
#


if __name__ == "__main__":
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='Update python virtual package requires: for latest python version')
    parser.add_argument('--pyversion', action='store', dest='pyversion', help='target python version', required=True)
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output', default=0)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='relarea')
    (args) = parser.parse_args()

    args.pyversion = args.pyversion.replace('.', '')

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    scan_hints(args)

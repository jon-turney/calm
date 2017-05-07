#!/usr/bin/env python3
#
# Copyright (c) 2016 Jon Turney
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
# Historically, cygwin was omitted from requires: and then upset added it back
# using the autodep mechanism
#
# Now we want to remove that complexity and treat it like a normal dependency,
# so this script fixes up setup.hints, adding cygwin to requires: where it
# should be
#

import argparse
import logging
import os
import re
import sys
import tarfile

import common_constants
import package


#
#
#
def main(args):
    # build package list
    packages = package.read_packages(args.rel_area, args.arch)

    for pn, po in packages.items():
        # package is source-only
        if 'skip' in po.hints:
            logging.info("%s is source-only" % (pn))
            continue

        # package requires: contains 'cygwin' already
        #
        # really this should use a whitespace boundary, not word boundary to
        # avoid matching cygwin-debug etc., but we just happen to know that only
        # debuginfo packages depend on cygwin-debuginfo which can safely be
        # skipped as they will never depend on cygwin
        requires = po.hints.get('requires', '')
        if re.search(r'\bcygwin\b', requires):
            logging.info("%s already has cygwin in requires" % (pn))
            continue

        # install tarfiles are all empty (usually because package is obsolete)
        if all([t.is_empty for t in po.tars.values()]):
            logging.info("%s has empty install tarfiles" % (pn))
            continue

        # search each install tarfile for executable files
        #
        # (any .exe or .dll file might have a dependency on cygwin1.dll, so for
        # simplicity we will assume that it does)
        amend = False
        for t in po.tars:
            logging.info("%s tarfile %s" % (pn, t))

            if re.search(r'-src\.tar', t):
                continue

            if po.tars[t].is_empty:
                continue

            with tarfile.open(os.path.join(args.rel_area, args.arch, po.path, t)) as a:
                if any(map(lambda f: re.search(r'^(bin|sbin|usr/bin|usr/lib|usr/libexec|usr/sbin)/.*\.(exe|dll|so|cmxs)$', f), a.getnames())):
                    logging.info("%s: matched in %s" % (pn, t))
                    amend = True
                    break

        if not amend:
            continue

        # adjust requires:, adding 'cygwin' to the end
        logging.warning("Adding 'cygwin' to requires: in setup.hint for package '%s'" % (pn))
        if len(requires) > 0:
            requires = requires + ' '
        po.hints['requires'] = requires + 'cygwin'

        # write the modified setup.hint file
        if 'parse-warnings' in po.hints:
            del po.hints['parse-warnings']
        if 'parse-errors' in po.hints:
            del po.hints['parse-errors']

        ofn = os.path.join(args.rel_area, args.arch, po.path, 'setup.hint')
        fn = os.path.join(args.rel_area, args.arch, po.path, 'setup.hint.modified')
        with open(fn, 'w') as f:
            for k, v in po.hints.items():
                print("%s: %s" % (k, v), file=f)

        # show any 'unexpected' changes in the setup.hint
        os.system("diff -u -I 'requires:' --ignore-blank-lines --ignore-space-change %s %s" % (ofn, fn))

        # replace the setup.hint file
        # (written this way so it doesn't spoil a hardlinked backup of the releasearea)
        os.rename(fn, ofn)

#
#
#
if __name__ == "__main__":
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='requires fixer')
    parser.add_argument('--arch', action='store', required=True, choices=common_constants.ARCHES)
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output', default=0)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    (args) = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    main(args)

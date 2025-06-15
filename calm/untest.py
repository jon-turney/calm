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
from . import tool_util


def untest(pvr):
    p, vr = tool_util.split(pvr)
    if not p:
        return

    if not tool_util.permitted(p):
        return

    # remove '^test:' lines from any package and subpackage hints
    removed = 0
    total = 0
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        for (dirpath, _subdirs, files) in os.walk(os.path.join(common_constants.FTP, arch, 'release', p)):
            for f in files:
                if re.match(r'.*-' + re.escape(vr) + r'.*\.hint$', f):
                    total = total + 1
                    fn = os.path.join(dirpath, f)

                    with open(fn) as fh:
                        content = fh.read()

                    if re.search(r'^test:', content, re.MULTILINE):
                        content = re.sub(r'^test:\s*$', '', content, count=0, flags=re.MULTILINE)

                        with open(fn, 'w') as fh:
                            fh.write(content)

                        logging.info("Removed test: label from %s" % os.path.relpath(fn, common_constants.FTP))
                        removed = removed + 1

    if removed == 0:
        logging.error("'%s' is not marked test" % pvr)
    else:
        logging.info("%d out of %d hints for '%s' version '%s' modified" % (removed, total, p, vr))


def main():
    parser = argparse.ArgumentParser(description='remove test: hint')
    parser.add_argument('package', nargs='+', metavar='SPVR')
    (args) = parser.parse_args()

    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format='untest: %(message)s')

    for p in args.package:
        untest(p)


if __name__ == "__main__":
    sys.exit(main())

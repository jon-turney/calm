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
import sys
import types

from . import common_constants
from . import db
from . import tool_util


def vault(pvr):
    p, vr = tool_util.split(pvr)
    if not p:
        return

    if not tool_util.permitted(p):
        return

    args = types.SimpleNamespace()
    args.htdocs = os.path.join(common_constants.HTDOCS, 'packages')

    db.vault_request_add(args, p, vr, os.environ['CYGNAME'])
    logging.info("package '%s' version '%s' marked as expirable" % (p, vr))


def main():
    parser = argparse.ArgumentParser(description='mark packages for vaulting')
    parser.add_argument('package', nargs='+', metavar='SPVR')
    (args) = parser.parse_args()

    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format='vault: %(message)s')

    for p in args.package:
        vault(p)


if __name__ == "__main__":
    sys.exit(main())

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

import logging
import os
import re

from . import common_constants
from . import maintainers


def split(pvr):
    # split name and vr
    match = re.match(r'^(.+?)-(\d.*)', pvr)
    if not match:
        logging.error("unable to determine package and version-release from '%s'" % (pvr))
        return (None, None)

    p = match.group(1)
    vr = match.group(2)

    return (p, vr)


def permitted(p):
    cygname = os.environ.get('CYGNAME', None)
    if not cygname:
        logging.error("who are you?")
        return False

    # CYGNAME is a maintainer for package
    pkg_list = maintainers.pkg_list(common_constants.PKGMAINT)
    if cygname in pkg_list[p].maintainers():
        return True

    # CYGNAME is a trusted maintainer
    if cygname in common_constants.TRUSTEDMAINT.split('/'):
        return True

    logging.error("package '%s' is not in the package list for maintainer '%s'" % (p, cygname))
    return False

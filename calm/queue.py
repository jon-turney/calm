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

from dirq.QueueSimple import QueueSimple
import logging
import os
import re

from . import uploads

QUEUE = 'package_queue'


#
#
#

def add(args, movelist, fromdir):
    if not hasattr(args, 'queuedir'):
        return

    queue_root = os.path.join(args.queuedir, 'dirq')
    upload_root = os.path.join(args.queuedir, 'uploads')

    dirq = QueueSimple(os.path.join(queue_root, QUEUE))

    # clean up empty directories
    dirq.purge()
    os.system('find %s -depth -mindepth 1 -type d -empty -delete' % upload_root)

    # are there any source packages in the filelist?
    srcpkgs = []
    for p in movelist:
        for f in movelist[p]:
            if re.search(r'-src.tar.(bz2|gz|lzma|xz)$', f):
                srcpkgs.append(os.path.join(p, f))

    # if so...
    #
    # XXX: really this should break things up into the set of files for each
    # source file
    if len(srcpkgs) >= 1:
        # keep all the files for comparison
        uploads.copy(args, movelist, fromdir, upload_root)

        # queue any srcpkgs
        for p in srcpkgs:
            if not args.dryrun:
                logging.debug("queuing source package %s for validation" % (p))
                dirq.add(p)

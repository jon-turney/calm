#!/usr/bin/env python
#
# Copyright 2001-2002 by Vinay Sajip. All Rights Reserved.
#
# Permission to use, copy, modify, and distribute this software and its
# documentation for any purpose and without fee is hereby granted,
# provided that the above copyright notice appear in all copies and that
# both that copyright notice and this permission notice appear in
# supporting documentation, and that the name of Vinay Sajip
# not be used in advertising or publicity pertaining to distribution
# of the software without specific, written prior permission.
# VINAY SAJIP DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE, INCLUDING
# ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL
# VINAY SAJIP BE LIABLE FOR ANY SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR
# ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER
# IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT
# OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#
# This file is part of the Python logging distribution. See
# http://www.red-dove.com/python_logging.html
#


import logging
import logging.handlers

from . import common_constants
from . import utils


class BufferingSMTPHandler(logging.handlers.BufferingHandler):
    def __init__(self,
                 toaddrs,
                 subject,
                 fromaddr='cygwin-no-reply@cygwin.com',
                 replytoaddr='cygwin-apps@cygwin.com',
                 logging_format='%(levelname)s: %(message)s'):
        logging.handlers.BufferingHandler.__init__(self, capacity=0)
        self.fromaddr = fromaddr
        self.toaddrs = toaddrs
        self.replytoaddr = replytoaddr
        self.subject = subject
        self.formatter = logging_format
        self.setFormatter(logging.Formatter(logging_format))

    def flush(self):
        if len(self.buffer) > 0:
            msg = ""
            for record in self.buffer:
                s = self.format(record)
                msg = msg + s + "\r\n"

            # append a summary of severities
            summary = {}

            for record in self.buffer:
                summary[record.levelname] = summary.get(record.levelname, 0) + 1

            msg = msg + 'SUMMARY: ' + ', '.join(['%d %s(s)' % (v, k) for (k, v) in summary.items()]) + "\r\n"

            hdr = {}
            hdr['From'] = self.fromaddr
            hdr['To'] = ','.join(self.toaddrs)
            hdr['Reply-To'] = self.replytoaddr
            hdr['Bcc'] = common_constants.ALWAYS_BCC
            hdr['Subject'] = self.subject
            hdr['X-Calm-Report'] = '1'

            utils.sendmail(hdr, msg)

            self.buffer = []

    def shouldFlush(self, record):
        # the capacity we pass to BufferingHandler is irrelevant since we
        # override shouldFlush so it never indicates we have reached capacity
        return False

    def __enter__(self):
        logging.getLogger().addHandler(self)
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.close()
        logging.getLogger().removeHandler(self)

        # process any exception in the with-block normally
        return False

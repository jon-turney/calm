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

from contextlib import ExitStack
import logging
import logging.handlers

import common_constants


class BufferingSMTPHandler(logging.handlers.BufferingHandler):
    def __init__(self,
                 toaddrs,
                 subject,
                 mailhost=common_constants.MAILHOST,
                 fromaddr='cygwin-no-reply@cygwin.com',
                 logging_format='%(message)s'):
        logging.handlers.BufferingHandler.__init__(self, capacity=0)
        self.mailhost = mailhost
        self.mailport = None
        self.fromaddr = fromaddr
        self.toaddrs = toaddrs
        self.subject = subject
        self.formatter = logging_format
        self.setFormatter(logging.Formatter(logging_format))

    def flush(self):
        if len(self.buffer) > 0:
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n" % (self.fromaddr, ','.join(self.toaddrs), self.subject)
            for record in self.buffer:
                s = self.format(record)
                msg = msg + s + "\r\n"

            # if toaddrs consists of the single address 'debug', just dump the mail we would have sent
            if self.toaddrs == ['debug']:
                print('-' * 40)
                print(msg)
                print('-' * 40)
            elif len(self.toaddrs) > 0:
                try:
                    import smtplib
                    port = self.mailport
                    if not port:
                        port = smtplib.SMTP_PORT
                    smtp = smtplib.SMTP(self.mailhost, port)
                    smtp.sendmail(self.fromaddr, self.toaddrs, msg)
                    smtp.quit()
                except:
                    self.handleError(self.buffer[0])  # first record

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


#
# we only want to mail the logs if the email option was used
# (otherwise use ExitStack() as a 'do nothing' context)
#

def mail_logs(enabled, toaddrs, subject):
    if enabled:
        return BufferingSMTPHandler(toaddrs, subject)

    return ExitStack()

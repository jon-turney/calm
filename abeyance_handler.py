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

import logging
from logging.handlers import BufferingHandler


# Loosely based on the "Buffering logging messages and outputting them
# conditionally" example from the python logging cookbook.
#
# AbeyanceHandler holds log output in a BufferingHandler.  When closed, it will
# pass all log output of retainLevel or higher to the target logger if any of
# the log output reaches thresholdLevel level, otherwise it discards all log
# output.

class AbeyanceHandler(BufferingHandler):
    def __init__(self, target, thresholdLevel, retainLevel):
        BufferingHandler.__init__(self, capacity=0)
        self.target = target
        self.thresholdLevel = thresholdLevel

        if retainLevel is None:
            retainLevel = thresholdLevel
        self.setLevel(retainLevel)

    def shouldFlush(self, record):
        # the capacity we pass to BufferingHandler is irrelevant since we
        # override shouldFlush so it never indicates we have reached capacity
        return False

    def close(self):
        # if there are any log records of thresholdLevel or higher ...
        if len(self.buffer) > 0:
            if any([record.levelno >= self.thresholdLevel for record in self.buffer]):
                # ... send all records to the target
                for record in self.buffer:
                    self.target.handle(record)

        self.target.close()

        # otherwise, just discard the buffers contents
        super().close()

    def __enter__(self):
        logging.getLogger().addHandler(self)
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.close()
        logging.getLogger().removeHandler(self)

        # process any exception in the with-block normally
        return False

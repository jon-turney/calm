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

#
# tests
#

import io
import os
import unittest

import calm.mkgitoliteconf

from .utils import compare_with_expected_file


class EntryPointsTest(unittest.TestCase):
    def test_mkgitoliteconf(self):
        pkglist = 'testdata/pkglist/cygwin-pkg-maint'
        output = io.StringIO()
        calm.mkgitoliteconf.do_main(pkglist, file=output)

        compare_with_expected_file(self, 'testdata/gitolite', output.getvalue(), basename='package-repos.conf')

    # XXX: TODO: test for mksetupini also

    @classmethod
    def setUpClass(cls):
        # testdata is located in the same directory as this file
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

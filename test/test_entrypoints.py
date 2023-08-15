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
import re
import types
import unittest

import calm.mkgitoliteconf
import calm.mksetupini

from .utils import compare_with_expected_file


class EntryPointsTest(unittest.TestCase):
    def test_mkgitoliteconf(self):
        self.maxDiff = None

        pkglist = 'testdata/pkglist/cygwin-pkg-maint'
        output = io.StringIO()
        calm.mkgitoliteconf.do_main(pkglist, file=output)

        compare_with_expected_file(self, 'testdata/gitolite', output.getvalue(), basename='package-repos.conf')

    def test_mksetupini(self):
        self.maxDiff = None

        args = types.SimpleNamespace()
        args.arch = 'x86_64'
        args.ignore_errors = True
        args.inifile = 'testdata/mksetupini/setup.ini'
        args.pkglist = None
        args.rel_area = 'testdata/relarea'
        args.release = 'repo-label'
        args.setup_version = None
        args.spell = False
        args.stats = False

        calm.mksetupini.do_main(args)

        with open(args.inifile) as inifile:
            results = inifile.read()

            # fix the timestamp to match expected
            results = re.sub('setup-timestamp: .*', 'setup-timestamp: 1680890562', results, count=1)
            results = re.sub('generated at .*', 'generated at 2023-04-07 18:02:42 GMT.', results, count=1)

            compare_with_expected_file(self, 'testdata/mksetupini', results, 'setup.ini')

    @classmethod
    def setUpClass(cls):
        # testdata is located in the same directory as this file
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

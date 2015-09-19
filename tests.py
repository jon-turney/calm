#!/usr/bin/env python3
#
# Copyright (c) 2015 Jon Turney
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

import filecmp
import logging
import os
import pprint
import types
import unittest

import hint
import pkg2html

class TestMain(unittest.TestCase):
    def test_hint_parser(self):
        self.maxDiff = None

        for (dirpath, subdirs, files) in os.walk('testdata/x86/release'):
            if 'setup.hint' in files:
                with self.subTest(package=os.path.basename(dirpath)):
                    logging.info('Reading %s' % os.path.join(dirpath, 'setup.hint'))
                    results = hint.setup_hint_parse(os.path.join(dirpath, 'setup.hint'))

                    # save results in a file
                    with open(os.path.join(dirpath, 'results'), 'w') as f:
                        pprint.pprint(results, stream=f, width=120)

                    # read expected from a file
                    with open(os.path.join(dirpath, 'expected')) as f:
                        expected = eval(f.read())

                    self.assertEqual(expected, results)

#
# something like "find -name results -exec sh -c 'cd `dirname {}` ; cp results
# expected' \;" can be used to update the expected output (after you have
# checking it to make sure it is really correct, of course :) )
#

    def test_html_writer(self):
        self.maxDiff = None

        htdocs = 'testdata/htdocs'
        args = types.SimpleNamespace()
        setattr(args, 'arch', 'x86')
        setattr(args, 'htdocs', htdocs)
        setattr(args, 'rel_area', 'testdata')
        setattr(args, 'dryrun', False)
        setattr(args, 'force', True)

        pkg2html.main(args)

        # compare the output files with expected
        for (dirpath, subdirs, files) in os.walk(htdocs):
            relpath = os.path.relpath(dirpath, htdocs)
            for f in files:
                results = os.path.join(htdocs, relpath, f)
                expected = os.path.join('testdata/htdocs.expected', relpath, f)
                if not filecmp.cmp(results, expected, shallow=False):
                    logging.info("%s different", os.path.join(relpath, f))
                    with open(results) as r, open(expected) as e:
                        self.assertMultiLineEqual(e.read(), r.read())
                else:
                    logging.info("%s identical", os.path.join(relpath, f))

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format='%(message)s')
    unittest.main()

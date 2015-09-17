#!/usr/bin/env python3
#
# tests
#

import os
import pprint
import unittest

import hint

class TestHintParser(unittest.TestCase):
    def test_hint(self):
        for (dirpath, subdirs, files) in os.walk('testdata/release'):
            if 'setup.hint' in files:
                with self.subTest(package=os.path.basename(dirpath)):
                    results = hint.setup_hint_parse(os.path.join(dirpath, 'setup.hint'))

                    # save results in a file
                    with open(os.path.join(dirpath, 'results'), 'w') as f:
                        pprint.pprint(results, stream=f, width=120)

                    # read expected from a file
                    with open(os.path.join(dirpath, 'expected')) as f:
                        expected = eval(f.read())

                    self.assertEqual(results, expected)

#
# something like "find -name results -exec sh -c 'cd `dirname {}` ; cp results
# expected' \;" can be used to update the expected output (after you have
# checking it to make sure it is really correct, of course :) )
#

if __name__ == '__main__':
    unittest.main()

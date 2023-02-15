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
# test helper functions
#

import os
import pprint


# write results to the file 'results'
# read expected from the file 'expected'
# compare them
def compare_with_expected_file(test, dirpath, results, basename=None):
    results_str = pprint.pformat(results, width=120)

    if basename:
        results_fn = basename + '.results'
        expected_fn = basename + '.expected'
    else:
        results_fn = 'results'
        expected_fn = 'expected'

    # save results in a file
    with open(os.path.join(dirpath, results_fn), 'w') as f:
        print(results_str, file=f)

    # read expected from a file
    with open(os.path.join(dirpath, expected_fn)) as f:
        expected = f.read().rstrip()

    test.assertMultiLineEqual(expected, results_str)

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

import collections
import contextlib
import os
import pprint


#
# a context to monkey-patch pprint so a multi-line OrderedDict repr appears as
# with python <3.5 (a dict, with lines ordered)
#
@contextlib.contextmanager
def pprint_patch():
    if isinstance(getattr(pprint.PrettyPrinter, '_dispatch', None), dict):
        orig = pprint.PrettyPrinter._dispatch[collections.OrderedDict.__repr__]
        pprint.PrettyPrinter._dispatch[collections.OrderedDict.__repr__] = patched_pprint_ordered_dict
        try:
            yield
        finally:
            pprint.PrettyPrinter._dispatch[collections.OrderedDict.__repr__] = orig
    else:
        yield


def patched_pprint_ordered_dict(self, obj, stream, indent, allowance, context, level):
    write = stream.write
    write('{')
    if self._indent_per_level > 1:
        write((self._indent_per_level - 1) * ' ')
    length = len(obj)
    if length:
        items = list(obj.items())
        self._format_dict_items(items, stream, indent, allowance + 1,
                                context, level)
    write('}')


#
# For python 3.12 a further change is needed so single-line OrderedDict appeads
# as a list of tuples rather than a dict
#
class CustomPrettyPrinter(pprint.PrettyPrinter):
    def format(self, obj, context, maxlevels, level):
        # special formatting for OrderedDict
        if isinstance(obj, collections.OrderedDict):
            return self.repr_ordered_dict(obj), True, False
        # Otherwise, use default behaviour
        return pprint.PrettyPrinter.format(self, obj, context, maxlevels, level)

    def repr_ordered_dict(self, obj):
        if len(obj):
            output = 'OrderedDict('
            items = list(obj.items())
            output += self.pformat(items)
            output += ')'
        else:
            output = 'OrderedDict()'

        return output


# write results to the file 'results'
# read expected from the file 'expected'
# compare them
def compare_with_expected_file(test, dirpath, results, basename=None):
    with pprint_patch():
        custom_pretty_printer = CustomPrettyPrinter(width=120)
        results_str = custom_pretty_printer.pformat(results)

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

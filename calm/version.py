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

import itertools
import logging
import re


#

def cmp(a, b):
    return (a > b) - (a < b)


#
# SetupVersion
#
# a helper class which implements the same version ordering as setup
#

class SetupVersion:
    def __init__(self, version_string):
        self._version_string = version_string

        # split version into [V, R], on the last '-', if any
        split = list(itertools.chain(version_string.rsplit('-', 1), ['']))[:2]

        # then split each part into numeric and non-numeric sequences.
        # numeric sequences have leading zeroes discarded
        for j, i in enumerate(['V', 'R']):
            setattr(self, '_' + i, [re.sub(r'^0+(\d)', r'\1', m.group(1), 1) for m in re.finditer(r'(\d+|\D+)', split[j])])

    def __str__(self):
        return '%s (V=%s R=%s)' % (self._version_string, str(self._V), str(self._R))

    # XXX: Implementing the __lt__ comparison operator in terms of the obsolete
    # __cmp__ operator is rather over-complicated.  If we really only need
    # __lt__ (which is sufficent to make this class sortable), then we should
    # just implement it directly.  For the moment, keep __cmp__ around in case
    # we need to do other comparisons. (in which case, see also functools
    # @total_ordering class decorator)
    def __lt__(self, other):
        return self.__cmp__(other) == -1

    def __cmp__(self, other):
        # warn about ill-specified comparisons
        # SetupVersion._warn_ambiguous_compare(self, other)

        # compare V
        c = SetupVersion._compare(self._V, other._V)
        if c != 0:
            return c

        # if V are the same, compare R
        return SetupVersion._compare(self._R, other._R)

    # comparison helper function
    @staticmethod
    def _compare(a, b):

        # compare each sequence in order
        for i in range(0, min(len(a), len(b))):
            # sort a non-digit sequence before a digit sequence
            if a[i].isdigit() != b[i].isdigit():
                return 1 if a[i].isdigit() else -1

            # compare as numbers
            if a[i].isdigit():
                # because leading zeros have already been removed, if one number
                # has more digits, it is greater
                c = cmp(len(a[i]), len(b[i]))
                if c != 0:
                    return c
                # fallthrough

            # compare lexicographically
            c = cmp(a[i], b[i])
            if c != 0:
                return c

        # if equal length, all components have matched, so equal
        # otherwise, the version with a suffix remaining is greater
        return cmp(len(a), len(b))

    # warn if the comparison of these versions is historically under-specified
    @staticmethod
    def _warn_ambiguous_compare(a, b):
        def classify(s):
            if len(s) == 0:
                return 'e'
            elif s[0].isdigit():
                return 'n'
            elif s[0] in '.-_':
                return s[0]
            elif s[0].isalpha():
                return 'a'
            return 'o'

        def is_ambiguous(a, b):
            ambiguous = False

            for i in range(0, min(len(a), len(b))):
                if classify(a[i]) != classify(b[i]):
                    ambiguous = True
                    break

            return ambiguous

        if is_ambiguous(a._V, b._V) or is_ambiguous(a._R, b._R):
            logging.warning("ordering of versions '%s' and '%s' may not be what you expect" % (a._version_string, b._version_string))

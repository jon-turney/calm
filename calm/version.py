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

import functools
import itertools
import re


#

def cmp(a, b):
    return (a > b) - (a < b)


#
# SetupVersion
#
# a helper class which implements the same version ordering as setup
#

@functools.total_ordering
class SetupVersion:
    def __init__(self, version_string):
        self._version_string = version_string

        # split release on the last '-', if any (default '')
        v, r = list(itertools.chain(version_string.rsplit('-', 1), ['']))[:2]

        # split epoch, on the first ':', if any (default '0')
        e, v = list(itertools.chain('0', v.split(':', 1)))[-2:]

        split = [e, v, r]

        # then split each part into numeric and alphabetic sequences
        # non-alphanumeric separators are discarded
        # numeric sequences have leading zeroes discarded
        for j, i in enumerate(['E', 'V', 'R']):
            setattr(self, i, split[j])
            sequences = re.finditer(r'(\d+|[a-zA-Z]+|[^a-zA-Z\d]+)', split[j])
            sequences = [m for m in sequences if not re.match(r'[^a-zA-Z\d]+', m.group(1))]
            sequences = [re.sub(r'^0+(\d)', r'\1', m.group(1), 1) for m in sequences]
            setattr(self, '_' + i, sequences)

    def __str__(self):
        return '%s (E=%s V=%s R=%s)' % (self._version_string, str(self._E), str(self._V), str(self._R))

    def __lt__(self, other):
        return self.__cmp__(other) == -1

    def __eq__(self, other):
        return self.__cmp__(other) == 0

    def __cmp__(self, other):
        # compare E
        c = SetupVersion._compare(self._E, other._E)
        if c != 0:
            return c

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

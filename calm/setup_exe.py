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
# extract version from setup executable
#

import argparse
import os
import re


#
# the setup binary contains a '%%% setup-version ' string identifying the
# version, but it's hard to read that when it's UPX packed.
#
# so instead, we expect the exe file to be a symlink to a file which encodes
# the version in it's name
#
# XXX: possibly we could work around this by placing the version string into
# a string resource and using upx's --keep-resource flag to keep that resource
# uncompressed
#

def extract_version(fn):
    # check the file exists
    if not os.path.exists(fn):
        raise FileNotFoundError

    # canonicalize the pathname
    fn = os.path.realpath(fn)

    match = re.search(r'setup-([\d\.]+).x86', fn)
    if match:
        return match.group(1)
    else:
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract version from setup executable')
    parser.add_argument('exe', action='store', nargs='?', metavar='filename', help='executable file')
    (args) = parser.parse_args()

    if args.exe:
        v = extract_version(args.exe)
        if v:
            print(v)
            exit(0)
        exit(1)

    parser.print_help()

# XXX:maybe this could make the filename from /www/sourceware/htdocs/cygwin and arch?

#!/usr/bin/env python3
#
# Copyright (c) 2017 Jon Turney
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
# Move a given source archive to src/ (assuming it is indentical in x86/ and
# x86_64/) and adjust hints appropriately.
#

import argparse
import copy
import os
import re
import sys

from . import common_constants
from . import hint

#
#
#


def hint_file_write(fn, hints):
    with open(fn, 'w') as f:
        for k, v in hints.items():
            print("%s: %s" % (k, v), file=f)

#
#
#


def dedup(archive, relarea):
    # split path and filename
    (path, filename) = os.path.split(archive)

    # parse tarfile name
    match = re.match(r'^(.+?)-(\d.*)-src\.tar\.(bz2|gz|lzma|xz)$', filename)

    if not match:
        print('tarfile name %s does not meet expectations' % (filename))
        sys.exit(1)

    p = match.group(1)
    vr = match.group(2)
    ext = match.group(3)

    # compute filenames
    to_filename = p + '-src-' + vr + '.tar.' + ext
    hint_filename = p + '-' + vr + '.hint'
    to_hint_filename = p + '-src-' + vr + '.hint'

    # read hints for both arches
    hints = {}
    for arch in ['x86', 'x86_64']:
        hint_pathname = os.path.join(relarea, arch, path, hint_filename)

        if not os.path.exists(hint_pathname):
            print('%s not found' % (hint_pathname))
            return 1

        hints[arch] = hint.hint_file_parse(hint_pathname, hint.pvr)

    if hints['x86'] != hints['x86_64']:
        print('hints for %s-%s differ between arches' % (p, vr))
        return 1

    # ensure target directory exists
    try:
        os.makedirs(os.path.join(relarea, 'src', path, p + '-src'))
    except FileExistsError:
        pass

    # move the src files to src/
    for arch in ['x86', 'x86_64']:
        print('%s -> %s' % (os.path.join(relarea, arch, path, filename), os.path.join(relarea, 'src', path, p + '-src', to_filename)))
        os.rename(os.path.join(relarea, arch, path, filename), os.path.join(relarea, 'src', path, p + '-src', to_filename))

    # write .hint file for new -src package
    src_hints = copy.copy(hints['x86'])

    if 'source' not in src_hints['sdesc']:
        sdesc = re.sub(r'"(.*)"', r'\1', src_hints['sdesc'])
        sdesc += ' (source code)'
        src_hints['sdesc'] = '"' + sdesc + '"'

    if 'requires' in src_hints:
        del src_hints['requires']

    if 'external-source' in src_hints:
        del src_hints['external-source']

    to_hint_pathname = os.path.join(relarea, 'src', path, p + '-src', to_hint_filename)
    print('writing %s' % (to_hint_pathname))
    hint_file_write(to_hint_pathname, src_hints)

    # adjust external-source in .hint for all subpackages
    for arch in ['x86', 'x86_64']:
        for (dirpath, subdirs, files) in os.walk(os.path.join(relarea, arch, path)):
            subpkg = os.path.basename(dirpath)
            filename = subpkg + '-' + vr + '.hint'
            if filename in files:
                hint_pathname = os.path.join(dirpath, filename)
                hints = hint.hint_file_parse(hint_pathname, hint.pvr)
                if ('skip' in hints):
                    # p was source only, so no package remains
                    print('removing %s' % (hint_pathname))
                    os.remove(hint_pathname)
                elif ('external-source' not in hints) or (hints['external-source'] == p):
                    hints['external-source'] = p + '-src'
                    print('writing %s' % (hint_pathname))
                    hint_file_write(hint_pathname, hints)

    return 0

#
#
#


def main():
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='Source package deduplicator')
    parser.add_argument('archive', metavar='ARCHIVE', nargs=1, help="source archive to deduplicate")
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    (args) = parser.parse_args()

    return dedup(args.archive[0], args.rel_area)

#
#
#

if __name__ == "__main__":
    sys.exit(main())

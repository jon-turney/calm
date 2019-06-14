#!/usr/bin/env python3
#
# Copyright (c) 2019 Jon Turney
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
# Fix hints for (probably source) packages consisting of just 'skip:'
#
# (cygport stopped generating these since 0.23.0)
#

import argparse
import os
import re
import shutil
import sys

from . import common_constants
from . import hint
from .version import SetupVersion


#
# write a hint file
#
def hint_file_write(fn, hints):
    with open(fn, 'w') as f:
        for k, v in hints.items():
            print("%s: %s" % (k, v), file=f)


#
# pick most popular item from a list
#
def pick(l):
    if not l:
        return None

    h = {}

    for i in l:
        h[i] = h.get(i, 0) + 1

    for i in sorted(h, key=h.get, reverse=True):
        print('%4d: %s' % (h[i], i))

    i = sorted(h, key=h.get, reverse=True)[0]
    # unanimous ?
    if h[i] == len(l):
        return i

    return None


#
# try to invent plausible information by looking at subpackages
#
def invent_from_subpackages(path, vr):
    sdesc_candidates = []
    category_candidates = []

    for (dirpath, subdirs, files) in os.walk(path):
        # debuginfo packages never have a good information
        if 'debuginfo' in dirpath:
            continue

        # consider sub-package hints
        for f in files:
            if re.match('^.*-' + re.escape(vr) + '.hint$', f):
                hints = hint.hint_file_parse(os.path.join(dirpath, f), hint.pvr)
                if 'sdesc' in hints:
                    # ... which doesn't contain 'Obsolete' etc.
                    if 'Obsolete' in hints['sdesc'] or '_obsolete' in hints['category']:
                        continue

                    # remove anything inside parentheses, or a single word after
                    # a hyphen, at the end of quoted sdesc
                    sdesc = hints['sdesc']
                    sdesc = re.sub(r'"(.*)"', r'\1', sdesc)
                    sdesc = re.sub(r'(\(.*?\))$', '', sdesc)
                    sdesc = re.sub(r' - \w*$', '', sdesc)
                    sdesc = sdesc.strip()
                    sdesc = '"' + sdesc + '"'

                    sdesc_candidates.append(sdesc)

                    # ignore 'Doc' category (on the basis that this usually a
                    # documentation subpackage)
                    if hints['category'] != 'Doc':
                        category_candidates.append(hints['category'])

    # Ignore a single tool/utility subpackage
    for t in ['utility', 'utilities', 'tool']:
        occurences = [c for c in sdesc_candidates if re.search(r'\b' + t + '\b', c.lower())]
        if len(occurences) == 1:
            sdesc_candidates.remove(occurences[0])

    # pick 'Libs' if that's a possibility
    category = pick(category_candidates)
    if not category and 'Libs' in category_candidates:
        category = 'Libs'

    return (pick(sdesc_candidates), category)


#
# try to invent plausible information by looking at more recent versions
#
def invent_from_other_versions(path, later_vrs):
    sdesc_candidates = []
    category_candidates = []

    pn = path.split(os.path.sep)[-1]
    for vr in later_vrs:
        f = pn + '-' + vr + '.hint'
        hints = hint.hint_file_parse(os.path.join(path, f), hint.pvr)

        if 'sdesc' in hints:
            sdesc_candidates.append(hints['sdesc'])
        if 'category' in hints:
            category_candidates.append(hints['category'])

    return (pick(sdesc_candidates), pick(category_candidates))


#
#
#
def fix_one_hint(dirpath, hintfile, vr, later_vrs):
    hints = hint.hint_file_parse(os.path.join(dirpath, hintfile), hint.pvr)

    hints.pop('parse-errors', None)
    hints.pop('parse-warnings', None)

    if ('skip' not in hints) or (len(hints) > 1):
        return (0, 0)

    # if hint only contains skip:, try to come up with plausible sdesc and category
    (sdesc, category) = invent_from_subpackages(dirpath, vr)
    if not (sdesc and category):
        (sdesc, category) = invent_from_other_versions(dirpath, later_vrs)
    if not (sdesc and category):
        print('couldn\'t invent hints for %s' % (hintfile))
        return (1, 0)

    hints['sdesc'] = sdesc
    hints['category'] = category

    if 'source' not in hints['sdesc']:
        sdesc = re.sub(r'"(.*)"', r'\1', hints['sdesc'])
        sdesc += ' (source)'
        hints['sdesc'] = '"' + sdesc + '"'

    print('writing invented hints for %s' % (hintfile))
    shutil.copy2(os.path.join(dirpath, hintfile), os.path.join(dirpath, hintfile + '.bak'))
    hint_file_write(os.path.join(dirpath, hintfile), hints)

    return (1, 1)


def fix_hints(rel_area, mode):
    skip_only = 0
    invented = 0

    for (dirpath, subdirs, files) in os.walk(rel_area):
        vrs = {}
        for f in files:
            match = re.match(r'^.*?-(\d.*).hint$', f)
            if match:
                vrs[match.group(1)] = f

        if vrs:
            if mode == 'newest':
                v = sorted(vrs, key=lambda v: SetupVersion(v), reverse=True)[0]
                f = vrs[v]
                vrs = {v: f}

            sorted_vrs = sorted(vrs, key=lambda v: SetupVersion(v))
            while sorted_vrs:
                vr = sorted_vrs.pop(0)
                (s, i) = fix_one_hint(dirpath, vrs[vr], vr, sorted_vrs)
                skip_only += s
                invented += i

    print('%d skip only hints, invented %d hints' % (skip_only, invented))


#
#
#


def main():
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='skip-only hint fixer')
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    parser.add_argument('--mode', action='store', metavar='all|newest', choices=['all', 'newest'], help="fix all hints, or (default) only for newest version", default='newest')
    (args) = parser.parse_args()

    return fix_hints(args.rel_area, args.mode)


#
#
#

if __name__ == "__main__":
    sys.exit(main())

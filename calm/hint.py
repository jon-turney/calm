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
# parser for .hint files
#

from collections import OrderedDict
import re
import argparse


# helper function to merge dicts
def merge_dicts(x, *y):
    z = x.copy()
    for i in y:
        z.update(i)
    return z

# types of key:
# 'multilineval' - always have a value, which may be multiline
# 'val'          - always have a value
# 'optval'       - may have an empty value
# 'noval'        - always have an empty value
keytypes = ['multilineval', 'val', 'optval', 'noval']

# kinds of hint file, and their allowed keys
setup, pvr, override = range(3)

commonkeys = {
    'ldesc': 'multilineval',
    'message': 'multilineval',
    'category': 'val',
    'external-source': 'val',
    'sdesc': 'val',
    'skip': 'noval',
}

versionkeys = {
    'curr': 'val',
    'prev': 'val',
    'test': 'val',
}

overridekeys = {
    'keep': 'val',
    'keep-count': 'val',
    'keep-days': 'val',
}

hintkeys = {}

hintkeys[setup] = merge_dicts(commonkeys, versionkeys, {
    'requires': 'optval',
})

hintkeys[pvr] = merge_dicts(commonkeys, {
    'requires': 'optval',
    # putative syntax for not yet implemented per-version dependencies
    # (depends could be an alias for requires in this kind of hint file)
    'depends': 'optval',
    'build-depends': 'optval',
    # mark the package as a test version
    'test': 'noval',
})

hintkeys[override] = merge_dicts(versionkeys, overridekeys)

# valid categories
categories = ['accessibility',
              'admin',
              'archive',
              'audio',
              'base',
              'comm',
              'database',
              'debug',
              'devel',
              'doc',
              'editors',
              'games',
              'gnome',
              'graphics',
              'interpreters',
              'kde',
              'libs',
              'lua',
              'lxde',
              'mail',
              'mate',
              'math',
              'mingw',
              'net',
              'ocaml',
              'office',
              'perl',
              'php',
              'publishing',
              'python',
              'ruby',
              'scheme',
              'science',
              'security',
              'shells',
              'sugar',
              'system',
              'tcl',
              'text',
              'utils',
              'video',
              'web',
              'x11',
              'xfce',
              '_obsolete',
              '_postinstalllast']


#
# A simple lexer to handle multi-line quoted values
#
# Historically, a multi-line quote is terminated only by a quote at the end of
# the line, and embedded quotes are transformed to single quotes.  So there is
# no escaping of embedded quotes, and no way to represent one.
#
# XXX: Fix the few packages which use embedded quotes, then we can switch this
# to a simpler character by character lexer, which just reads until next
# newline, and next quote when we encounter a quote.
#
def item_lexer(c):
    i = -1
    lines = c.splitlines()

    while i < len(lines)-1:
        i = i + 1
        o = lines[i]

        # discard lines starting with '#'
        if o.startswith('#'):
            continue

        o = o.strip()

        # discard empty lines
        if not o:
            continue

        # line containing quoted text
        if o.count('"') == 2:
            yield (i, o, None)
            continue

        # if the line contains an opening quote
        if '"' in o:
            # continue reading lines till closing quote
            while i < len(lines)-1:
                i = i + 1
                # multi-line quoted text preserves any leading space used for
                # indentation, but removes any trailing space
                o = o + '\n' + lines[i].rstrip()
                # multi-line quoted text is only terminated by a quote at the
                # end of the line
                if o.endswith('"'):
                    yield (i, o, None)
                    break
            else:
                yield (i, o, "unterminated quote")

            continue

        # an unquoted line
        yield (i, o, None)


# parse the file |fn| as a .hint file of kind |kind|
def hint_file_parse(fn, kind):
    hints = OrderedDict()
    errors = []
    warnings = []

    assert(kind in hintkeys)

    with open(fn, 'rb') as f:
        c = f.read()

        # validate that .hint file is UTF-8 encoded
        try:
            c = c.decode('utf-8')

            # parse as key:value items
            for (i, item, error) in item_lexer(c):

                if (error):
                    errors.append('%s at line %d' % (error, i))

                if (item.count('"') != 0) and (item.count('"') != 2):
                    errors.append('embedded quote at line %d' % (i))

                # key:value
                match = re.match(r'^([^:\s]+):\s*(.*)$', item, re.DOTALL)
                if match:
                    key = match.group(1)
                    value = match.group(2)

                    if key not in hintkeys[kind]:
                        errors.append('unknown key %s at line %d' % (key, i))
                        continue
                    type = hintkeys[kind][key]

                    # check if the key occurs more than once
                    if key in hints:
                        errors.append('duplicate key %s' % (key))

                    # check the value meets any key-specific constraints
                    if (type == 'val') and (len(value) == 0):
                        errors.append('%s has empty value' % (key))

                    if (type == 'noval') and (len(value) != 0):
                        errors.append("%s has non-empty value '%s'" % (key, value))

                    # validate all categories are in the category list (case-insensitively)
                    if key == 'category':
                        for c in value.split():
                            if c.lower() not in categories:
                                errors.append("unknown category '%s'" % (c))

                    # verify that value for ldesc or sdesc is quoted
                    # (genini forces this)
                    if key in ['sdesc', 'ldesc']:
                        if not (value.startswith('"') and value.endswith('"')):
                            errors.append("%s value '%s' should be quoted" % (key, value))

                    # if sdesc ends with a '.', warn and fix it
                    if key == 'sdesc':
                        if re.search(r'\."$', value):
                            warnings.append("sdesc ends with '.'")
                            value = re.sub(r'\."$', '"', value)

                    # warn if sdesc contains '  '
                    if key == 'sdesc':
                        if '  ' in value:
                            warnings.append("sdesc contains '  '")

                    # only 'ldesc' and 'message' are allowed a multi-line value
                    if (type != 'multilineval') and (len(value.splitlines()) > 1):
                        errors.append("key %s has multi-line value" % (key))

                    # message must have an id and some text
                    if key == 'message':
                        if not re.match(r'(\S+)\s+(\S.*)', value):
                            errors.append('message value must have id and text')

                    # warn if value starts with a quote followed by whitespace
                    if re.match(r'^"[ \t]+', value):
                        warnings.append('value for key %s starts with quoted whitespace' % (key))

                    # store the key:value
                    hints[key] = value
                else:
                    errors.append("unknown setup construct '%s' at line %d" % (item, i))

            # for setup and pvr kinds, if 'skip' isn't present, 'category' and
            # 'sdesc' must be
            # XXX: genini also requires 'requires' but that seems wrong
            if 'skip' not in hints and kind != override:
                mandatory = ['category', 'sdesc']
                for k in mandatory:
                    if k not in hints:
                        errors.append("required key '%s' missing" % (k))

            # warn if ldesc and sdesc seem transposed
            #
            # (Unfortunately we can't be totally strict about this, as some
            # packages like to repeat the basic description in ldesc in every
            # subpackage, but add to sdesc to distinguish the subpackages)
            if 'ldesc' in hints:
                if len(hints['sdesc']) > 2*len(hints['ldesc']):
                    warnings.append('sdesc is much longer than ldesc')

            # sort requires: as differences in ordering are uninteresting
            if 'requires' in hints:
                hints['requires'] = ' '.join(sorted(hints['requires'].split()))

        except UnicodeDecodeError:
            errors.append('invalid UTF-8')

    if errors:
        hints['parse-errors'] = errors

    if warnings:
        hints['parse-warnings'] = warnings

    return hints


#
#
#

def main(args):
    status = 0

    for fn in args.files:
        hints = hint_file_parse(fn, setup)

        if args.verbose > 1:
            print(hints)

        if 'parse-warnings' in hints:
            if args.verbose > 0:
                for l in hints['parse-warnings']:
                    print('%s: %s' % (fn, l))
            status = 1

        if 'parse-errors' in hints:
            for l in hints['parse-errors']:
                print('%s: %s' % (fn, l))
            status = 255

    return status

#
#
#

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='.hint file validator')
    parser.add_argument('files', nargs='*', metavar='filename', help='list of files')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output', default=0)

    (args) = parser.parse_args()

    exit(main(args))

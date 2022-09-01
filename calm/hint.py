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

import argparse
import re
from collections import OrderedDict

try:
    import license_expression
except ModuleNotFoundError:
    licensing = None
else:
    # reach inside license_expression to add custom license ids we permit
    json = license_expression.get_license_index()
    extra_licenses = [
        'Linux-man-pages-copyleft',  # requires SPDX license-list 3.15
        'Public-Domain',
        'XVIEW',
    ]
    for l in extra_licenses:
        json.append({"spdx_license_key": l})
    licensing = license_expression.build_spdx_licensing(json)

# types of key:
# 'multilineval' - always have a value, which may be multiline
# 'val'          - always have a value
# 'optval'       - may have an empty value
# 'noval'        - always have an empty value
keytypes = ['multilineval', 'val', 'optval', 'noval']

# kinds of hint file, and their allowed keys
pvr, override, spvr = range(3)

hintkeys = {}

commonkeys = {
    'ldesc': 'multilineval',
    'category': 'val',
    'sdesc': 'val',
    'test': 'noval',   # mark the package as a test version
    'version': 'val',  # version override
    'disable-check': 'val',
    'notes': 'val',    # tool notes; not significant to calm itself
}

hintkeys[pvr] = commonkeys.copy()
hintkeys[pvr].update({
    'message': 'multilineval',
    'external-source': 'val',
    'requires': 'optval',
    'obsoletes': 'optval',
    'provides': 'val',
    'conflicts': 'val',
})

hintkeys[spvr] = commonkeys.copy()
hintkeys[spvr].update({
    'skip': 'noval',   # in all spvr hints, but ignored
    'homepage': 'val',
    'build-depends': 'optval',
    'license': 'val',
})

hintkeys[override] = {
    'keep': 'val',
    'keep-count': 'val',
    'keep-count-test': 'val',
    'keep-days': 'val',
    'keep-superseded-versions': 'noval',
    'disable-check': 'val',
    'replace-versions': 'val',
}

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
              'source',  # added to all source packages created by deduplicator to ensure they have a category
              'sugar',
              'system',
              'tcl',
              'text',
              'utils',
              'video',
              'virtual',
              'web',
              'x11',
              'xfce',
              '_obsolete',
              ]


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

    while i < len(lines) - 1:
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
            while i < len(lines) - 1:
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


def split_trim_sort_join(hint, splitchar, joinchar=None):
    if joinchar is None:
        joinchar = splitchar + ' '

    return joinchar.join(sorted([s.strip() for s in hint.split(splitchar)]))


# parse the file |fn| as a .hint file of kind |kind|
def hint_file_parse(fn, kind, strict=False):
    hints = OrderedDict()
    errors = []
    warnings = []

    assert (kind in hintkeys) or (kind is None)

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

                    if kind is not None:
                        if key not in hintkeys[kind]:
                            errors.append('unknown key %s at line %d' % (key, i))
                            continue
                        valtype = hintkeys[kind][key]

                        # check if the key occurs more than once
                        if key in hints:
                            errors.append('duplicate key %s' % (key))

                        # check the value meets any key-specific constraints
                        if (valtype == 'val') and (len(value) == 0):
                            errors.append('%s has empty value' % (key))

                        if (valtype == 'noval') and (len(value) != 0):
                            errors.append("%s has non-empty value '%s'" % (key, value))

                        # only 'ldesc' and 'message' are allowed a multi-line value
                        if (valtype != 'multilineval') and (len(value.splitlines()) > 1):
                            errors.append("key %s has multi-line value" % (key))

                    # validate all categories are in the category list (case-insensitively)
                    if key == 'category':
                        for c in value.split():
                            if c.lower() not in categories:
                                errors.append("unknown category '%s'" % (c))

                    if key in ['sdesc', 'ldesc']:
                        # verify that value for ldesc or sdesc is quoted (genini
                        # forces this)
                        if not (value.startswith('"') and value.endswith('"')):
                            errors.append("%s value '%s' should be quoted" % (key, value))

                        # warn about and fix common typos in ldesc/sdesc
                        value, msg = typofix(value)
                        if msg:
                            warnings.append("%s in %s" % (','.join(msg), key))

                    # if sdesc ends with a '.', warn and fix it
                    if key == 'sdesc':
                        if re.search(r'\."$', value):
                            warnings.append("sdesc ends with '.'")
                            value = re.sub(r'\."$', '"', value)

                    # if sdesc contains '  ', warn and fix it
                    if key == 'sdesc':
                        if '  ' in value:
                            warnings.append("sdesc contains '  '")
                            value = value.replace('  ', ' ')

                    # message must have an id and some text
                    if key == 'message':
                        if not re.match(r'(\S+)\s+(\S.*)', value):
                            errors.append('message value must have id and text')

                    # license must be a valid spdx license expression
                    if key == 'license' and licensing:
                        try:
                            licensing.parse(value, strict=True)
                            le = licensing.validate(value, strict=True)
                        except license_expression.ExpressionParseError as e:
                            errors.append('errors parsing license expression: %s' % (e))
                        except license_expression.ExpressionError as e:
                            errors.append('errors validating license expression: %s' % (e))
                        else:
                            if not le.normalized_expression:
                                errors.append('errors in license expression: %s' % (le.errors))
                            elif le.original_expression != le.normalized_expression:
                                errors.append("license expression: '%s' normalizes to '%s'" % (value, le.normalized_expression))

                    # warn if value starts with a quote followed by whitespace
                    if re.match(r'^"[ \t]+', value):
                        warnings.append('value for key %s starts with quoted whitespace' % (key))

                    # store the key:value
                    hints[key] = value
                else:
                    errors.append("unknown construct '%s' at line %d" % (item, i))

            if ('skip' in hints) and (len(hints) == 1):
                errors.append("hint only contains skip: key, please update to cygport >= 0.22.0")

            # for the pvr kind, 'category' and 'sdesc' must be present
            # (genini also requires 'requires' but that seems wrong)
            # for the spvr kind, 'homepage' must be present for new packages
            if (kind == pvr) or (kind == spvr):
                mandatory = ['category', 'sdesc']
                if (kind == spvr) and strict:
                    mandatory.append('homepage')

                for k in mandatory:
                    if k not in hints:
                        errors.append("required key '%s' missing" % (k))

                suggested = []
                if (kind == spvr) and strict:
                    suggested.append('license')

                for k in suggested:
                    if k not in hints:
                        warnings.append("key '%s' missing" % (k))

            # warn if ldesc and sdesc seem transposed
            #
            # (Unfortunately we can't be totally strict about this, as some
            # packages like to repeat the basic description in ldesc in every
            # subpackage, but add to sdesc to distinguish the subpackages)
            if 'ldesc' in hints:
                if len(hints['sdesc']) > 2 * len(hints['ldesc']):
                    warnings.append('sdesc is much longer than ldesc')

            # sort these hints, as differences in ordering are uninteresting
            if 'requires' in hints:
                hints['requires'] = split_trim_sort_join(hints['requires'], None, ' ')

            if 'build-depends' in hints:
                if ',' in hints['build-depends']:
                    hints['build-depends'] = split_trim_sort_join(hints['build-depends'], ',')
                else:
                    hints['build-depends'] = split_trim_sort_join(hints['build-depends'], None, ', ')

            if 'obsoletes' in hints:
                # obsoletes is specified as comma separated, but cygport writes it space separated at the moment...
                if ',' in hints['obsoletes']:
                    hints['obsoletes'] = split_trim_sort_join(hints['obsoletes'], ',')
                else:
                    hints['obsoletes'] = split_trim_sort_join(hints['obsoletes'], None, ', ')

            if 'replace-versions' in hints:
                hints['replace-versions'] = split_trim_sort_join(hints['replace-versions'], None, ' ')

        except UnicodeDecodeError:
            errors.append('invalid UTF-8')

    if errors:
        hints['parse-errors'] = errors

    if warnings:
        hints['parse-warnings'] = warnings

    return hints


# write hints |hints| to file |fn|
def hint_file_write(fn, hints):
    with open(fn, 'w') as f:
        for k, v in hints.items():
            print("%s: %s" % (k, v), file=f)


#
# words that Cygwin package maintainers apparently can't spell correctly
#

words = [
    (' accomodates ', ' accommodates '),
    (' consistant ', ' consistent '),
    (' examing ', ' examining '),
    (' extremly ', ' extremely '),
    (' interm ', ' interim '),
    (' procesors ', ' processors '),
    (' utilitzed ', ' utilized '),
    (' utilties ', ' utilities '),
]


def typofix(v):
    msg = []

    for (wrong, right) in words:
        if wrong in v:
            v = v.replace(wrong, right)
            msg.append('%s -> %s' % (wrong.strip(), right.strip()))

    return v, msg


#
#
#

def main(args):
    status = 0

    for fn in args.files:
        hints = hint_file_parse(fn, spvr if fn.endswith('src.hint') else pvr)

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

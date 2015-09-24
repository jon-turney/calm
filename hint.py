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
# parser for setup.hint files
#

import re
import argparse

# keys which always have a value which may be multiline
multilinevalkeys = [ 'ldesc', 'message']
# keys which always have a value
valkeys = [ 'curr', 'prev', 'test', 'category', 'external-source', 'sdesc' ]
# keys which may have an empty value
optvalkeys = [ 'requires' ]
# keys which must have an empty value
novalkeys = ['skip' ]
# obsolete keys used by autodep mechanism we accept as valid for the moment
obsoletekeys = [ 'autodep', 'noautodep', 'incver_ifdep' ]

hintkeys = multilinevalkeys + valkeys + optvalkeys + novalkeys + obsoletekeys

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
                yield (i, o , "unterminated quote")

            continue

        # an unquoted line
        yield (i, o, None)

def setup_hint_parse(fn):
    hints = {}
    errors = []
    warnings = []

    with open(fn, 'rb') as f:
        c = f.read()

        # validate that setup.hint is UTF-8 encoded
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

                    if not key in hintkeys:
                        errors.append('unknown setup key %s at line %d' % (key, i))
                        continue

                    # check if the key occurs more than once
                    if key in hints:
                        errors.append('duplicate key %s' % (key))

                    # store the key:value
                    hints[key] = value

                    # check the value meets any key-specific constraints
                    if (key in valkeys) and (len(value) == 0):
                        errors.append('%s has empty value' % (key))

                    if (key in novalkeys) and (len(value) != 0):
                        errors.append("%s has non-empty value '%s'" % (key, value))

                    # validate that sdesc doesn't contain ':', as that prefix is removed
                    if key == 'sdesc':
                        if ':' in value:
                            warnings.append("sdesc contains ':'")

                    # only 'ldesc' and 'message' are allowed a multi-line value
                    if (key not in multilinevalkeys) and (len(value.splitlines()) > 1):
                        errors.append("key %s has multi-line value" % (key))

                    # message must have an id and some text
                    if key == 'message':
                        if not re.match(r'(\S+)\s+(\S.*)', value):
                            errors.append('message value must have id and text')

                    # warn if value starts with a quote followed by whitespace
                    if re.match(r'^"[ \t]+', value):
                        warnings.append('value for key %s starts with quoted whitespace' % (key))

                    # XXX: perhaps quotes around the value should be mandatory
                    # for some keys?
                else:
                    errors.append("unknown setup construct '%s' at line %d" % (item, i))

            # if 'skip' isn't present, 'category' and 'sdesc' must be
            if 'skip' not in hints:
                mandatory = ['category', 'sdesc']
                for k in mandatory:
                    if k not in hints:
                        errors.append("required key '%s' missing")

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
        hints = setup_hint_parse(fn)

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
    parser = argparse.ArgumentParser(description='setup.hint validator')
    parser.add_argument('files', nargs='*', metavar='filename', help='list of files')
    parser.add_argument('-v', '--verbose', action='count', dest = 'verbose', help='verbose output', default=0)

    (args) = parser.parse_args()

    exit(main(args))

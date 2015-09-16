#!/usr/bin/env python3
#
# parser for setup.hint files
#

import re
import argparse

# keys which always have a value which may be multiline
multilinevalkeys = [ 'ldesc', 'message']
# keys which always have a value
valkeys = [ 'curr', 'prev', 'test', 'category', 'external-source', 'autodep', 'noautodep', 'sdesc' ]
# keys which may have an empty value
optvalkeys = [ 'requires' ]
# keys which must have an empty value
novalkeys = ['skip' ]
# obsolete key used by _update_info_dir we accept as valid for the moment
obsoletekeys = [ 'incver_ifdep' ]

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
                        errors.append('unknown setup key %s at line %d' % (fn, key, i))
                        err_count = err_count + 1
                        continue

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
                            errors.append("sdesc '%s' contains ':'" % (value))

                    # only 'ldesc' and 'message' are allowed a multi-line value
                    if (key not in multilinevalkeys) and (len(value.splitlines()) > 1):
                        errors.append("key %s has multi-line value" % (key))

                    # message must have an id and some text
                    if key == 'message':
                        if not re.match(r'(\S+)\s+(\S.*)', value):
                            errors.append('message value must have id and text')
                else:
                    errors.append("unknown setup construct '%s' at line %d" % (item, i))

        except UnicodeDecodeError:
            errors.append('invalid UTF-8')

    if errors:
        hints['parse-errors'] = errors

    return hints

#
#
#

def main(files):
    status = 0

    for fn in files:
        hints = setup_hint_parse(fn)

        if 'parse-errors' in hints:
            for l in hints['parse-errors']:
                print('%s: %s' % (fn, l))
#            status = 255
        else:
#            print('%s: ok' % fn)
            pass

    return status

#
#
#

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='setup.hint validator')
    parser.add_argument('files', nargs='*', metavar='filename', help='list of files')
    (args) = parser.parse_args()

    exit(main(args.files))

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

import logging
import re
from enchant import DictWithPWL
from enchant.checker import SpellChecker
from enchant.tokenize import Filter


#
#
#

class DescFilter(Filter):
    # acronym may start with a digit (e.g. 3GPP), contains two or more capital
    # letters (e.g. IP), may also end with a digit (e.g. MP3), and may be
    # pluralized (e.g. DLLs)
    _acronym_pattern = re.compile(r'^\d?[A-Z]{2,}\d?(|s)')
    _url_pattern = re.compile(r'.+://.+')
    _module_pattern = re.compile(r'.+::.+')
    _path_pattern = re.compile(r'^/.+')

    _commands = ['apng2gif', 'gif2apng']

    #
    def _skip(self, word):
        # skip acronyms
        if self._acronym_pattern.match(word):
            # print("%s is an acronyn" % word)
            return True

        # ignore things which look like URLs
        if self._url_pattern.match(word):
            # print("%s is a URL" % word)
            return True

        # ignore things which look like perl/ruby module names (contain ::)
        if self._module_pattern.match(word):
            # print("%s is a module name" % word)
            return True

        # ignore things which look like paths
        if self._path_pattern.match(word):
            # print("%s is a path name" % word)
            return True

        # commands containing digits won't be recognized as single words, so we
        # arrange to skip those also
        if word in self._commands:
            return True

        return False


def spellcheck_hints(args, packages):
    spelldict = DictWithPWL('en-US')
    chkr = SpellChecker(spelldict, filters=[DescFilter])
    misspellings = {}

    # add technical words not in spell-checking dictionary
    wordlist = []
    with open('words.txt') as f:
        for w in f:
            # strip any trailing comment
            w = re.sub(r'#.*$', '', w)
            # strip any whitespace
            w = w.strip()
            spelldict.add(w)
            wordlist.append(w.lower())
            # XXX: for the moment, to reduce the set of errors, ignore the fact
            # that words.txt gives a canonical capitalization, and accept any
            # capitalization
            spelldict.add(w.lower())
            spelldict.add(w.capitalize())

    # add all package names as valid words
    for p in packages:
        for w in re.split('[_-]', p):
            # remove punctuation characters
            w = re.sub(r'[+]', '', w)
            # strip off any trailing numbers
            w = re.sub(r'[\d.]*$', '', w)

            # both with and without any lib prefix
            for w1 in [w, re.sub(r'^lib', '', w)]:
                # add the package name unless it exists in the list above, which
                # will give a canonical capitalization
                if w.lower() not in wordlist:
                    spelldict.add(w.lower())
                    spelldict.add(w)
                    spelldict.add(w.capitalize())

    # for each package
    for p in packages.keys():
        # debuginfo packages have uninteresting, auto-generated text which
        # contains the package name
        if p.endswith('-debuginfo'):
            continue

        # spell-check the spell-checkable keys
        for k in ['sdesc', 'ldesc', 'message']:
            if k in packages[p].hints:
                chkr.set_text(packages[p].hints[k])
                # XXX: this is doing all the work to generate suggestions, which
                # we then ignore, so could be written much more efficiently
                for err in chkr:
                    # logging.error("package '%s', hint '%s': Is '%s' a word?" % (p, k, err.word))
                    misspellings.setdefault(err.word, 0)
                    misspellings[err.word] += 1

    # summarize
    for c in sorted(misspellings, key=misspellings.get, reverse=True):
        print('%16s: %4d' % (c, misspellings[c]))

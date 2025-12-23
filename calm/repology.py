#!/usr/bin/env python3
#
# Copyright (c) 2022 Jon Turney
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
# get 'latest upstream version' information from repology.org (note that this
# may not exist for some packages, e.g. where upstream doesn't do releases)
#

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections import namedtuple
from enum import Enum, auto, unique

from .version import SetupVersion

REPOLOGY_API_URL = 'https://repology.org/api/v1/projects/'
last_check = 0
last_data = {}

LegacyData = namedtuple('LegacyData', ['version_re', 'ignores', 'transform', 'source'])
use_legacy = {
    'automake': LegacyData(r'\d.\d+', ['+'], None, None),
    'gnupg': LegacyData(r'\d', [], lambda v: '' if v == '1' else v, None),
    'gtk': LegacyData(r'\d', ['3.9', '+', '-'], None, None),
    'gtksourceview': LegacyData(r'\d', [], None, None),
    'guile': LegacyData(r'\d.\d', ['+'], None, None),
    'python': LegacyData(r'\d.\d+', ['-', '_', '~'], lambda v: v.replace('.', ''), None),
    'python-docs': LegacyData(r'\d.\d+', ['-', '_', '~'], lambda v: v.replace('.', ''), lambda v: 'python' + v + '-doc'),
    'qt': LegacyData(r'\d', ['p'], None, None),
    'xdelta': LegacyData(r'\d', [], lambda v: '' if v == '1' else v, None),
}

RepologyData = namedtuple('RepologyData', ['upstream_version', 'repology_project_name'])


@unique
class UnknownVersion(Enum):
    noscheme = auto()
    unique = auto()
    unclassified = auto()
    unknown = auto()

    def __str__(self):
        return self.name


def repology_fetch_data():
    repology_data = {}
    last_pn = ''

    while True:
        url = REPOLOGY_API_URL
        if last_pn:
            url = url + last_pn + '/'
        url += '?inrepo=cygwin'

        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'CygwinUpstreamVersionFetch/1.0 +http://cygwin.com/')

        try:
            r = urllib.request.urlopen(request, timeout=600)
        except urllib.error.URLError as e:
            logging.error("consulting repology for upstream versions failed: %s" % (e.reason))
            return {}
        except ConnectionResetError as e:
            logging.error("consulting repology for upstream versions failed: %s" % (e))
            return {}

        j = json.loads(r.read().decode('utf-8'))

        for pn in sorted(j.keys()):
            p = j[pn]

            # first, pick out the version(s) which repology has called newest, and
            # if needed, also pick out latest version for legacy packages
            newest_version = []
            legacy_versions = {}

            for i in p:
                v = i['version']
                if i['status'] == 'newest':
                    newest_version.append(v)

                if (pn in use_legacy) and (i['status'] in ['legacy', 'outdated', 'newest']):
                    ld = use_legacy[pn]
                    prefix_re = ld.version_re

                    m = re.match(r'^(' + prefix_re + r')', v)
                    if m:
                        prefix = m.group(1)
                    else:
                        continue

                    if ld.transform:
                        prefix = ld.transform(prefix)

                    # blacklist versions containing certain substrings
                    # (pre-release versions etc.)
                    if any(ignore in v for ignore in ld.ignores):
                        continue

                    # repology doesn't identify the highest legacy version, so
                    # we have to that ourselves
                    if SetupVersion(v) > SetupVersion(legacy_versions.get(prefix, '0')):
                        legacy_versions[prefix] = v

            # if we couldn't find a newest_version...
            if not newest_version:
                # if everything is noscheme, that's the reason
                if all(i['status'] in ['noscheme', 'rolling'] for i in p):
                    newest_version.append(UnknownVersion.noscheme)
                # if this package is unique to cygwin, that's the reason
                elif all(i['status'] in ['unique'] for i in p):
                    newest_version.append(UnknownVersion.unique)
                # if repology's not sure what upstream this package belongs to
                elif pn.endswith('unclassified'):
                    newest_version.append(UnknownVersion.unclassified)
                # if repology (probably correctly) thinks there's something
                # weird about this package...
                else:
                    newest_version.append(UnknownVersion.unknown)
                    logging.info("repology can't help with latest version for project %s" % (pn))

            # next, assign that version to all the corresponding cygwin source
            # packages
            #
            # (multiple cygwin source packages can correspond to a single
            # canonical repology package name, e.g. foo and mingw64-arch-foo)
            for i in p:
                if i['repo'] == "cygwin":
                    source_pn = i['srcname']

                    if pn in use_legacy:
                        # if source package name contains legacy version
                        #
                        # the empty string is (in some cases), a possible value
                        # for prefix, so ensure that longest match wins
                        prefix = None
                        for p in sorted(legacy_versions):
                            source = pn + p

                            if use_legacy[pn].source:
                                source = use_legacy[pn].source(p)

                            if source in source_pn:
                                prefix = p

                        if prefix is not None:
                            upstream_version = [legacy_versions[prefix]]
                        else:
                            upstream_version = newest_version

                    else:
                        # otherwise, just use the newest version(s)
                        upstream_version = newest_version

                    repology_data[source_pn] = RepologyData(upstream_version, pn)

        if pn == last_pn:
            break
        else:
            last_pn = pn

        # rate-limit individual API calls to once per second
        time.sleep(1)

    return repology_data


# when repology reports multiple 'newest' versions due to altver, pick the one
# which splits into the same number of numeric and alphabetic sequences
def seqmatch(bv, uv):
    if len(uv) <= 1:
        return uv[0]

    seq_count = len(SetupVersion(bv)._V)
    for v in uv:
        if len(SetupVersion(bv)._V) == seq_count:
            return v

    return uv[0]


def annotate_packages(args, packages):
    global last_check
    global last_data

    # rate-limit fetching data to daily
    if (time.time() - last_check) < (24 * 60 * 60):
        logging.info("not consulting %s due to ratelimit" % (REPOLOGY_API_URL))
    else:
        logging.info("consulting %s" % (REPOLOGY_API_URL))
        repology_data = repology_fetch_data()
        if repology_data:
            last_data = repology_data

        last_check = time.time()

    for pn in last_data:
        spn = pn + '-src'
        if spn in packages:
            packages[spn].upstream_version = seqmatch(packages[spn].best_version, last_data[pn].upstream_version)
            packages[spn].repology_project_name = last_data[pn].repology_project_name

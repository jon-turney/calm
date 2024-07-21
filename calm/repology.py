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
import time
import urllib.error
import urllib.request
from collections import namedtuple

from .version import SetupVersion

REPOLOGY_API_URL = 'https://repology.org/api/v1/projects/'
last_check = 0
last_data = {}

LegacyData = namedtuple('LegacyData', ['version', 'ignores'])
use_legacy = {'qt': [LegacyData('5', []),
                     LegacyData('4', []),
                     LegacyData('3', [])],
              'gtk': [LegacyData('3', ['3.9', '+']),
                      LegacyData('2', [])],
              'gtksourceview': [LegacyData('2', []),
                                LegacyData('3', []),
                                LegacyData('4', []),
                                LegacyData('5', []),
                                ]
              }


def repology_fetch_versions():
    upstream_versions = {}
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

            # first, pick out the version which repology has called newest, and
            # if needed, also pick out latest version for legacy packages
            newest_version = None
            legacy_versions = {}

            for i in p:
                v = i['version']
                if i['status'] == 'newest':
                    newest_version = v

                if (pn in use_legacy) and (i['status'] in ['legacy', 'outdated']):
                    prefix = None
                    for ld in use_legacy[pn]:
                        if v.startswith(ld.version):
                            prefix = ld.version
                            break

                    if not prefix:
                        continue

                    # blacklist versions containing substrings (pre-release
                    # versions etc.)
                    if any(ignore in v for ignore in ld.ignores):
                        continue

                    # repology doesn't identify the highest legacy version, so
                    # we have to that ourselves
                    if SetupVersion(v) > SetupVersion(legacy_versions.get(prefix, '0')):
                        legacy_versions[prefix] = v

            if not newest_version:
                continue

            # next, assign that version to all the corresponding cygwin source
            # packages
            #
            # (multiple cygwin source packages can correspond to a single
            # canonical repology package name, e.g. foo and mingw64-arch-foo)
            for i in p:
                if i['repo'] == "cygwin":
                    source_pn = i['srcname']

                    # if package name contains legacy version
                    if pn in use_legacy:
                        prefix = None
                        for ld in use_legacy[pn]:
                            if (pn + ld.version) in source_pn:
                                prefix = ld.version

                        if prefix and prefix in legacy_versions:
                            upstream_versions[source_pn] = legacy_versions[prefix]
                            continue

                    # otherwise, just use the newest version
                    upstream_versions[source_pn] = newest_version

        if pn == last_pn:
            break
        else:
            last_pn = pn

        # rate-limit individual API calls to once per second
        time.sleep(1)

    return upstream_versions


def annotate_packages(args, packages):
    global last_check
    global last_data

    # rate-limit fetching data to daily
    if (time.time() - last_check) < (24 * 60 * 60):
        logging.info("not consulting %s due to ratelimit" % (REPOLOGY_API_URL))
    else:
        logging.info("consulting %s" % (REPOLOGY_API_URL))
        uv = repology_fetch_versions()
        if uv:
            last_data = uv

    for pn in last_data:
        spn = pn + '-src'
        for arch in packages:
            if spn in packages[arch]:
                packages[arch][spn].upstream_version = last_data[pn]

    last_check = time.time()

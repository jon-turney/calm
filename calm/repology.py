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
import urllib.request

REPOLOGY_API_URL = 'https://repology.org/api/v1/projects/'
last_check = 0


def repology_fetch_versions():
    upstream_versions = {}
    last_pn = ''

    while True:
        url = REPOLOGY_API_URL
        if last_pn:
            url = url + last_pn + '/'
        url += '?inrepo=cygwin'

        r = urllib.request.urlopen(url)
        j = json.loads(r.read().decode('utf-8'))

        for pn in sorted(j.keys()):
            p = j[pn]

            # first, pick out the version which repology has called newest
            newest_version = None
            for i in p:
                if i['status'] == 'newest':
                    newest_version = i['version']
                    break
            else:
                continue

            # next, assign that version to all the corresponding cygwin source
            # packages
            #
            # (multiple cygwin source packages can correspond to a single
            # canonical repology package name, e.g. foo and mingww64-arch-foo)
            for i in p:
                if i['repo'] == "cygwin":
                    source_pn = i['srcname']
                    upstream_versions[source_pn] = newest_version

        if pn == last_pn:
            break
        else:
            last_pn = pn

    return upstream_versions


def annotate_packages(args, packages):
    # rate limit to daily
    global last_check
    if (time.time() - last_check) < (24 * 60 * 60):
        logging.info("not consulting %s due to ratelimit" % (REPOLOGY_API_URL))
        return

    logging.info("consulting %s" % (REPOLOGY_API_URL))
    uv = repology_fetch_versions()

    for pn in uv:
        spn = pn + '-src'
        for arch in packages:
            if spn in packages[arch]:
                packages[arch][spn].upstream_version = uv[pn]

    last_check = time.time()

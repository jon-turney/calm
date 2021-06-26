#!/usr/bin/env python3
#
# Copyright (c) 2020 Jon Turney
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

import functools
import logging
import os
import re
import shutil
import socket
import tarfile
import urllib.request
import urllib.error
import xtarfile

from . import hint


def read_cygport(dirpath, tf):
    try:
        with xtarfile.open(os.path.join(dirpath, tf), mode='r') as a:
            cygports = [m for m in a.getmembers() if m.name.endswith('.cygport')]

            if len(cygports) != 1:
                logging.info('srcpkg %s contains %d .cygport files' % (tf, len(cygports)))
                return None

            f = a.extractfile(cygports[0])
            content = f.read()

    except tarfile.ReadError:
        logging.error("srcpkg %s is not a valid compressed archive" % tf)
        return None

    try:
        content = content.decode()
    except UnicodeDecodeError:
        logging.error("utf8 decode error for .cygport in srcpkg %s" % tf)
        content = content.decode(errors='replace')

    # fold any line-continuations
    content = content.replace('\\\n', '')

    return content


class NoRedirection(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):
        return response

    https_response = http_response


@functools.lru_cache(maxsize=None)
def follow_redirect(homepage):
    opener = urllib.request.build_opener(NoRedirection)
    opener.addheaders = [('User-Agent', 'calm')]
    request = urllib.request.Request(homepage, method='HEAD')
    try:
        response = opener.open(request, timeout=60)
        if response.code in [301, 308]:
            return response.headers['Location']
    except (ConnectionResetError, ValueError, socket.timeout, urllib.error.URLError) as e:
        logging.warning('error %s checking homepage:%s' % (e, homepage))
    return homepage


def _fix_homepage_src_hint(hints, dirpath, _hf, tf):
    # already present?
    if 'homepage' in hints:
        homepage = hints['homepage']
    else:
        # crack open corresponding -src.tar and parse homepage out from .cygport
        logging.debug('examining %s' % tf)
        content = read_cygport(dirpath, tf)

        homepage = None
        if content:
            for l in content.splitlines():
                match = re.match(r'^\s*HOMEPAGE\s*=\s*("|)([^"].*)\1', l)
                if match:
                    if homepage:
                        logging.warning('multiple HOMEPAGE lines in .cygport in srcpkg %s', tf)
                    pn = os.path.basename(dirpath)
                    homepage = match.group(2)
                    homepage = re.sub(r'\$({|)(PN|ORIG_PN|NAME)(}|)', pn, homepage)

        if homepage and '$' in homepage:
            logging.warning('unknown shell parameter expansions in HOMEPAGE="%s" in .cygport in srcpkg %s' % (homepage, tf))
            homepage = None

        if not homepage:
            logging.info('cannot determine homepage: from srcpkg %s' % tf)
            return False

        logging.info('adding homepage:%s to hints for srcpkg %s' % (homepage, tf))

    # check if redirect?
    redirect_homepage = follow_redirect(homepage)

    # trivial URL transformations aren't interesting
    if redirect_homepage.endswith('/') and not homepage.endswith('/'):
        homepage = homepage + '/'

    # check for http -> https redirects
    if redirect_homepage != homepage:
        if redirect_homepage == homepage.replace('http://', 'https://'):
            logging.warning('homepage:%s permanently redirects to %s, fixing' % (homepage, redirect_homepage))
            homepage = redirect_homepage
        else:
            # don't warn about intra-site redirects
            if (not redirect_homepage.startswith(homepage)) and (redirect_homepage.startswith('http')):
                logging.warning('homepage:%s permanently redirects to %s' % (homepage, redirect_homepage))

    # changed?
    if homepage != hints.get('homepage', None):
        hints['homepage'] = homepage
        return True

    return False


def _fix_invalid_keys_hint(hints, _dirpath, hf, _tf):
    # eliminate keys that aren't appropriate to the package type
    if hf.endswith('-src.hint'):
        valid_keys = hint.hintkeys[hint.spvr]
    else:
        valid_keys = hint.hintkeys[hint.pvr]

    changed = False
    for k in list(hints.keys()):
        if k not in valid_keys:
            logging.debug("discarding invalid key '%s:' from hint '%s'" % (k, hf))
            hints.pop(k, None)
            changed = True

    return changed


def fix_hint(dirpath, hf, tf, problems):
    hintfile = os.path.join(dirpath, hf)
    hints = hint.hint_file_parse(hintfile, None)

    hints.pop('parse-warnings', None)
    if 'parse-errors' in hints:
        logging.error('invalid hints %s' % hf)
        return

    changed = False
    if 'homepage' in problems:
        changed = _fix_homepage_src_hint(hints, dirpath, hf, tf)
    if 'invalid_keys' in problems:
        changed = _fix_invalid_keys_hint(hints, dirpath, hf, tf) or changed

    # write updated hints
    if changed:
        shutil.copy2(hintfile, hintfile + '.bak')
        hint.hint_file_write(hintfile, hints)

    return changed

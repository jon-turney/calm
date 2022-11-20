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
import urllib.error
import urllib.request

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


def _parse_cygport_var(dirpath, tf, var):
    # crack open corresponding -src.tar and parse var out from .cygport
    logging.debug('examining %s' % tf)
    content = read_cygport(dirpath, tf)

    value = None
    if content:
        for l in content.splitlines():
            match = re.match(r'^\s*' + var + r'\s*=\s*("|)([^"].*)\1', l)
            if match:
                if value:
                    logging.warning('multiple %s lines in .cygport in srcpkg %s' % (var, tf))
                pn = os.path.basename(dirpath)
                value = match.group(2)
                value = re.sub(r'\$({|)(PN|ORIG_PN|NAME)(}|)', pn, value)

    if value and '$' in value:
        logging.warning('unknown shell parameter expansions in %s="%s" in .cygport in srcpkg %s' % (var, value, tf))
        value = None

    return value


class NoRedirection(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):
        return response

    https_response = http_response


@functools.lru_cache(maxsize=None)
def follow_redirect(homepage):
    opener = urllib.request.build_opener(NoRedirection)
    opener.addheaders = [('User-Agent', 'calm')]
    try:
        request = urllib.request.Request(homepage, method='HEAD')
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
        homepage = _parse_cygport_var(dirpath, tf, 'HOMEPAGE')

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


# for specific packages, map some human-readable license texts to SPDX expressions
licmap = [
    ('Apache License, Version 2',             'Apache-2.0',                             ['meson', 'ninja']),
    ('BSD 3-Clause',                          'BSD-3-Clause',                           ['libsolv', 'mingw64-i686-libsolv', 'mingw64-x86_64-libsolv']),
    ('BSD3/GPLv2+',                           'BSD-3-Clause AND GPL-2.0-or-later',      ['dash']),
    ('CC BY-SA 3.0',                          'CC-BY-SA-3.0',                           ['dmalloc']),
    ('GNU General Public License, Version 2', 'GPL-2.0-only',                           ['buildbot-slave', 'buildbot-worker']),
    ('GNU General Public License, Version 3', 'GPL-3.0-or-later',                       ['osslsigncode']),
    ('GPL',                                   'GPL-2.0-or-later',                       ['cpuid']),
    ('GPL',                                   'GPL-3.0-or-later',                       ['units']),
    ('GPLv2+',                                'GPL-2.0-or-later',                       ['grep', 'gzip', 'readline']),
    ('GPLv2+FontEmbExc/OFL-1.1',              'GPL-2.0-or-later WITH Font-exception-2.0 OR OFL-1.1',
                                                                                        ['unifont']),
    ('GPLv3+',                                'GPL-3.0-or-later',                       ['bison', 'wget']),
    ('LGPLv2.1+/GPLv2+',                      'LGPL-2.1-or-later AND GPL-2.0-or-later', ['libgcrypt']),
    ('LGPLv3+/GPLv2+/GPLv3+/LGPLv2+',         '(LGPL-3.0-or-later OR GPL-2.0-or-later) AND GPL-3.0-or-later',
                                                                                        ['libidn', 'mingw64-i686-libidn', 'mingw64-x86_64-libidn']),
    ('LGPLv3+/GPLv2+/GPLv3+/Unicode2016',     '(LGPL-3.0-or-later OR GPL-2.0-or-later) AND GPL-3.0-or-later AND Unicode-DFS-2016',
                                                                                        ['libidn2', 'mingw64-i686-libidn2', 'mingw64-x86_64-libidn2']),
    ('MIT License',                           'MIT',                                    ['python-future']),
    ('MIT-like',                              'curl',                                   ['curl', 'mingw64-i686-curl', 'mingw64-x86_64-curl']),
    ('MIT-like',                              'Linux-man-pages-copyleft',               ['man-pages-linux', 'man-pages-posix']),
    ('MIT-like',                              'BSD-Source-Code',                        ['vttest']),
    ('Public domain',                         'BSD-3-Clause AND Public-Domain',         ['tzdata', 'tzcode']),
    ('SGI Free Software License B',           'SGI-B-2.0',                              ['khronos-opengl-registry']),
    ('Sun OpenLook',                          'XVIEW',                                  ['xview']),
]


def _fix_license_src_hint(hints, dirpath, _hf, tf):
    # already present?
    if 'license' in hints:
        lic = hints['license']
    else:
        lic = _parse_cygport_var(dirpath, tf, 'LICENSE')

        if not lic:
            logging.info('cannot determine license: from srcpkg %s' % tf)
            return False

        pn = dirpath.split(os.path.sep)[-1]
        for (human, spdx, pl) in licmap:
            if (pn in pl) and (lic.lower() == human.lower()):
                lic = spdx
                logging.info("converted license text '%s' to SPDX license expression '%s'" % (human, spdx))
                break

        logging.info('adding license:%s to hints for srcpkg %s' % (lic, tf))

    # changed?
    if lic != hints.get('license', None):
        hints['license'] = lic
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
    if 'license' in problems:
        changed = _fix_license_src_hint(hints, dirpath, hf, tf) or changed

    # write updated hints
    if changed:
        shutil.copy2(hintfile, hintfile + '.bak')
        hint.hint_file_write(hintfile, hints)

    return changed

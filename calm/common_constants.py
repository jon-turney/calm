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

import os

#
# project constants
#
# Generally these are defaults for values settable via command line options
#

# base directory for maintainer upload directories
HOMEDIR = '/sourceware/cygwin-staging/home'

# the 'release area', contains all released files, which are rsync'ed to mirrors
FTP = '/var/ftp/pub/cygwin'

# logs are emailed to these addresses if any errors occurred
EMAILS = ','.join(list(map(lambda m: m + '@sourceware.org', ['corinna', 'yselkowitz'])) + ['Stromeko@NexGo.DE'])

# every email we send is bcc'd to these addresses
ALWAYS_BCC = 'jturney@sourceware.org, yselkowitz@sourceware.org'

# these maintainers can upload orphaned packages as well
ORPHANMAINT = "Yaakov Selkowitz"

# architectures we support
ARCHES = ['x86', 'x86_64']

# base directory for HTML output
HTDOCS = '/www/sourceware/htdocs/cygwin/'

# the list of packages with maintainers
PKGMAINT = '/www/sourceware/htdocs/cygwin/cygwin-pkg-maint'

# removed files archive directory
VAULT = '/sourceware/snapshot-tmp/cygwin'

# SMTP smarthost
MAILHOST = 'localhost'

# defaults for package freshness
DEFAULT_KEEP_COUNT = 3
DEFAULT_KEEP_DAYS = 0

# different values to be used when we are not running on sourceware.org, but my
# test system...
if os.uname()[1] == 'tambora':
    FTP = '/var/ftp/pub/cygwin-test'
    EMAILS = 'jon.turney@dronecode.org.uk'
    ALWAYS_BCC = ''
    MAILHOST = 'allegra'

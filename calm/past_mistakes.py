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
# For things we really want to warn on but there are annoyingly many existing
# uses, we have a list of existing uses we can forgive, so we can warn on new
# uses.
#

# package names which have been used with versions containing a hyphen
hyphen_in_version = [
    'ctorrent',
    'dialog',
    'dialog-debuginfo',
    'email',
    'email-debuginfo',
    'fdupes',
    'gendef',
    'gendef-debuginfo',
    'gtk3-engines-unico',
    'gtk3-engines-unico-debuginfo',
    'hidapi',
    'hidapi-debuginfo',
    'libdialog-devel',
    'libdialog11',
    'libdialog12',
    'libhidapi-devel',
    'libhidapi0',
    'libmangle',
    'libmangle-debuginfo',
    'libncurses-devel',
    'libncurses10',
    'libncursesw-devel',
    'libncursesw10',
    'man-pages-posix',
    'mingw64-i686-hidapi',
    'mingw64-i686-hidapi-debuginfo',
    'mingw64-x86_64-hidapi',
    'mingw64-x86_64-hidapi-debuginfo',
    'ncurses',
    'ncurses-debuginfo',
    'ncurses-demo',
    'ncursesw',
    'ncursesw-demo',
    'recode',
    'recode-debuginfo',
    'socat',
    'socat-debuginfo',
    'tack',
    'tack-debuginfo',
    'xemacs-mule-sumo',
    'xemacs-sumo',
    'xfs',
    'xfs-debuginfo',
    'xview',
    'xview-devel',
]

# cygport places this into the requires of every debuginfo package
self_requires = [
    'cygwin-debuginfo'
]

# these are packages which only contain data, symlinks or scripts and thus
# function as their own source
self_source = [
    'R_autorebase',
    '_update-info-dir',
    'base-cygwin',
    'base-files',  # older versions were self-source, but current one isn't
    'chere',
    'cygcheck-dep',
    'gcc4-core',
    'gcc4-g++',
    'tesseract-ocr-deu',  # unclear how these are delivered by upstream and how they are packaged
    'tesseract-ocr-deu-f',
    'tesseract-ocr-eng',
    'tesseract-ocr-fra',
    'tesseract-ocr-ita',
    'tesseract-ocr-nld',
    'tesseract-ocr-por',
    'tesseract-ocr-spa',
    'tesseract-ocr-vie',
    'tesseract-training-core',
    'tesseract-training-deu',
    'tesseract-training-eng',
    'tesseract-training-fra',
    'tesseract-training-ita',
    'tesseract-training-nld',
    'tesseract-training-por',
    'tesseract-training-spa',
    'tesseract-training-vie',
]

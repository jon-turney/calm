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
    'email',
    'email-debuginfo',
    'fdupes',
    'fftw3',
    'fftw3-debuginfo',
    'fftw3-doc',
    'gendef',
    'gendef-debuginfo',
    'gtk3-engines-unico',
    'gtk3-engines-unico-debuginfo',
    'hidapi',
    'hidapi-debuginfo',
    'libfftw3_3',
    'libfftw3-devel',
    'libfftw3-omp3',
    'libhidapi-devel',
    'libhidapi0',
    'libmangle',
    'libmangle-debuginfo',
    'man-pages-posix',
    'mingw64-i686-hidapi',
    'mingw64-i686-hidapi-debuginfo',
    'mingw64-x86_64-hidapi',
    'mingw64-x86_64-hidapi-debuginfo',
    'recode',
    'recode-debuginfo',
    'socat',
    'socat-debuginfo',
    'tack',
    'tack-debuginfo',
    'xemacs-mule-sumo',
    'xemacs-sumo',
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

# these are packages which currently have versions different to all the other
# install packages from the same source package
nonunique_versions = [
    'bzr-debuginfo',              # debuginfo from NMU needs to age out
    'cgdb-debuginfo',             # debuginfo from NMU needs to age out
    'gnome-panel-doc',
    'gtk2.0-engines-svg',
    'guile-doc',
    'guile-gv',                   # dropped pending guile-2
    'info',                       # something went wrong with package build?
    'libcaca-doc',                # dropped pending fix for current doxygen
    'libfltk-doc',
    'libical_cxx-devel',
    'libquota-devel',             # no longer provided by e2fsprogs
    'libturbojpeg',               # no number means it isn't considered an old soversion
    'minizip',
    'mutter-doc',
    'ocaml-camlp4',               # ocaml-camlp4 removed from ocaml distribution after 4.01.0
    'ocaml-gv',                   # dropped pending ocaml cleanup
    'python-clang',               # split out from clang
    'python3-clang',              # split out from clang
    'sng-debuginfo',
    'socat-debuginfo',            # debuginfo for test version when curr has no debuginfo
    'sqlite3-zlib',               # sqlite3-zlib removed in 3.8.10, use sqlite3-compress instead
    'texinfo-debuginfo',          # something went wrong with package build?
    'w3m-img',
]

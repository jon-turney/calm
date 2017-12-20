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
    'dolphin',                    # split out from kde-baseapps
    'dolphin4',                   # dropped from kde-baseapps
    'gcc-java',                   # dropped from gcc 6
    'girepository-AppStream1.0',  # moved from appstream-glib to appstream
    'girepository-SpiceClientGtk2.0',  # gtk2 dropped from spice-gtk
    'gnome-panel-doc',
    'gtk2.0-engines-svg',
    'guile-doc',
    'kdepasswd',                  # dropped from split kde-baseapps
    'kdialog',                    # split out from kde-baseapps
    'keditbookmarks',             # split out from kde-baseapps
    'kexi',                       # split out from calligra
    'kfind',                      # split out from kde-baseapps
    'kfilereplace',               # split out from kdewebdev
    'kimagemapeditor',            # split out from kdewebdev
    'klinkstatus',                # split out from kdewebdev
    'konqueror',                  # split out from kde-baseapps
    'libatomic_ops-devel',        # separated out from libgc
    'libcaca-doc',                # dropped pending fix for current doxygen
    'libfltk-doc',
    'libgcj-common',              # dropped from gcc 6
    'libical_cxx-devel',
    'libquota-devel',             # no longer provided by e2fsprogs
    'libturbojpeg',               # no number means it isn't considered an old soversion
    'libtxc_dxtn',                # split out from s2tc
    'libtxc_dxtn-devel',          # split out from s2tc
    'mingw64-i686-qt5-declarative-debuginfo',    # dropped in 5.9
    'mingw64-i686-qt5-tools-debuginfo',          # dropped in 5.9
    'mingw64-i686-spice-gtk2.0',  # gtk2 dropped from spice-gtk
    'mingw64-x86_64-qt5-declarative-debuginfo',  # dropped in 5.9
    'mingw64-x86_64-qt5-tools-debuginfo',        # dropped in 5.9
    'mingw64-x86_64-spice-gtk2.0',  # gtk2 dropped from spice-gtk
    'minizip',
    'mutter-doc',
    'ocaml-camlp4',               # ocaml-camlp4 removed from ocaml distribution after 4.01.0
    'okular4-part',               # changed to okular5-part in 17.04
    'python-spiceclientgtk',      # gtk2 dropped from spice-gtk
    'sng-debuginfo',
    'socat-debuginfo',            # debuginfo for test version when curr has no debuginfo
    'sqlite3-zlib',               # sqlite3-zlib removed in 3.8.10, use sqlite3-compress instead
    'transfig-debuginfo',         # after transfig 3.2.6 source is included in xfig
    'w3m-img',
]

# packages with an empty install file, no source, but aren't obsolete
empty_but_not_obsolete = [
    'libpopt0',        # version 1.16-1 was empty
    'libpopt-devel',   # version 1.16-1 was empty (x86_64)
]

# packages with timestamp anomalies
mtime_anomalies = [
    'gcc-java',
    'gcc-tools-epoch2-autoconf',
    'glproto',
    'gv-debuginfo',
    'libgcj-common',
    'libgcj16',
    'python-gtk2.0',
    'python-gtk2.0-demo',
    'python-gtk2.0-devel',
    'python-wx',  # timestamps reset when split out from wxWidgets
    'subversion',  # 1.8 and 1.9 might be built in either order...
    'subversion-debuginfo',
    'subversion-devel',
    'subversion-gnome',
    'subversion-httpd',
    'subversion-perl',
    'subversion-python',
    'subversion-ruby',
    'subversion-tools',
    'xextproto',
]

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

# packages with historical versions containing a hyphen
hyphen_in_version = {
    'ctorrent': ['1.3.4-dnh3.2'],
    'email': ['3.2.1-git', '3.2.3-git'],
    'email-debuginfo': ['3.2.1-git', '3.2.3-git'],
    'fdupes': ['1.50-PR2'],
    'fftw3': ['3.3.6-pl1'],
    'fftw3-debuginfo': ['3.3.6-pl1'],
    'fftw3-doc': ['3.3.6-pl1'],
    'gendef': ['1.0-svn2931'],
    'gendef-debuginfo': ['1.0-svn2931'],
    'hidapi': ['0.8.0-rc1'],
    'hidapi-debuginfo': ['0.8.0-rc1'],
    'libfftw3_3': ['3.3.6-pl1'],
    'libfftw3-devel': ['3.3.6-pl1'],
    'libfftw3-omp3': ['3.3.6-pl1'],
    'libhidapi-devel': ['0.8.0-rc1'],
    'libhidapi0': ['0.8.0-rc1'],
    'libmangle': ['1.0-svn2930'],
    'libmangle-debuginfo': ['1.0-svn2930'],
    'man-pages-posix': ['2013-a'],
    'mingw64-i686-hidapi': ['0.8.0-rc1'],
    'mingw64-i686-hidapi-debuginfo': ['0.8.0-rc1'],
    'mingw64-x86_64-hidapi': ['0.8.0-rc1'],
    'mingw64-x86_64-hidapi-debuginfo': ['0.8.0-rc1'],
    'recode': ['3.7-beta2'],
    'recode-debuginfo': ['3.7-beta2'],
    'tack': ['1.07-20130713', '1.07-20150606'],
    'tack-debuginfo': ['1.07-20130713', '1.07-20150606'],
    'xemacs-mule-sumo': ['2007-04-27'],
    'xemacs-sumo': ['2007-04-27'],
    'xview': ['3.2p1.4-28'],
    'xview-devel': ['3.2p1.4-28'],
}

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
#
# don't add to this list, use 'disable-check: unique-version' in pvr.hint instead
nonunique_versions = [
    'bzr-debuginfo',              # debuginfo from NMU needs to age out
    'cgdb-debuginfo',             # debuginfo from NMU needs to age out
    'dolphin4',                   # dropped from kde-baseapps
    'gcc-java',                   # dropped from gcc 6
    'girepository-SpiceClientGtk2.0',  # gtk2 dropped from spice-gtk
    'gnome-panel-doc',
    'gtk2.0-engines-svg',
    'kdepasswd',                  # dropped from split kde-baseapps
    'kexi',                       # split out from calligra
    'kfilereplace',               # split out from kdewebdev
    'libcaca-doc',                # dropped pending fix for current doxygen
    'libflint',                   # no number means it isn't considered an old soversion
    'libfltk-doc',
    'libgcj-common',              # dropped from gcc 6
    'libical_cxx-devel',
    'libquota-devel',             # no longer provided by e2fsprogs
    'libturbojpeg',               # no number means it isn't considered an old soversion
    'libtxc_dxtn',                # split out from s2tc
    'mingw64-i686-poppler-qt4',   # dropped since 0.62.0
    'mingw64-i686-spice-gtk2.0',  # gtk2 dropped from spice-gtk
    'mingw64-x86_64-poppler-qt4',  # dropped since 0.62.0
    'mingw64-x86_64-spice-gtk2.0',  # gtk2 dropped from spice-gtk
    'minizip',
    'mutter-doc',
    'ocaml-camlp4',               # ocaml-camlp4 removed from ocaml distribution after 4.01.0
    'okular4-part',               # changed to okular5-part in 17.04
    'python-spiceclientgtk',      # gtk2 dropped from spice-gtk
    'sng-debuginfo',
    'sqlite3-zlib',               # sqlite3-zlib removed in 3.8.10, use sqlite3-compress instead
    'w3m-img',
]

# empty install packages, that aren't obsolete
#
# don't add to this list, use 'disable-check: empty-obsolete' in pvr.hint instead
empty_but_not_obsolete = {
    'freeglut-doc': ['3.0.0-1', '3.2.1-1'],                # should be obsoleted by libglut-devel which contains doc now
    'isl': ['0.16.1-1'],                                   # useless empty package, not autosupressed as it has depends
    'libpopt-devel': ['1.16-1'],                           # version 1.16-1 was empty (x86_64)
    'libpopt0': ['1.16-1'],                                # version 1.16-1 was empty
    'mbedtls': ['2.16.0-1'],                               # useless empty package, not autosupressed as it has depends
    'mpclib': ['1.1.0-1'],                                 # useless empty package, not autosupressed as it has depends
    'mpfr': ['4.0.2-1'],                                   # useless empty package, not autosupressed as it has depends
    'serf-debuginfo': ['1.3.8-1', '1.3.9-1'],              # empty presumably due to build problems
}

# packages with timestamp anomalies
#
# don't add to this list, use 'disable-check: curr-most-recent' in override.hint instead
mtime_anomalies = [
    'gcc-java',
    'gcc-tools-epoch2-autoconf',
    'gcc-tools-epoch2-autoconf-src',
    'gv-debuginfo',
    'libgcj-common',
    'libgcj16',
    'python-gtk2.0',
    'subversion',  # 1.8 and 1.9 might be built in either order...
    'subversion-debuginfo',
    'subversion-devel',
    'subversion-gnome',
    'subversion-httpd',
    'subversion-perl',
    'subversion-python',
    'subversion-ruby',
    'subversion-src',
    'subversion-tools',
]

# packages with maintainer anomalies
#
# don't add to this list, fix the package
maint_anomalies = {
    'libelf0': ['0.8.13-2'],  # libelf is called libelf0 in x86 arch
    'libelf0-devel': ['0.8.13-2'],
}

# packages missing obsoletions
#
# don't add to this list, fix the package (e.g. by adding the needed obsoletions)
# (an enhancement to cygport might be necessary to support doing that for
# debuginfo packages?)
missing_obsolete = {
    'filemanager-actions-debuginfo': ['caja-actions-debuginfo'],
    'guile2.2-debuginfo': ['guile-debuginfo'],
    'librsync-debuginfo': ['rdiff-debuginfo'],
    'man-db-debuginfo': ['man-debuginfo'],        # contain conflicting files
    'procps-ng-debuginfo': ['procps-debuginfo'],  # contain conflicting files
    'python2-debuginfo': ['python-debuginfo'],    # contain conflicting files
    'python-dbus-debuginfo': ['python3-dbus-debuginfo'],
    'rxvt-unicode-debuginfo': ['rxvt-unicode-X-debuginfo'],
    'spectacle-debuginfo': ['ksnapshot-debuginfo'],
    'xfce4-pulseaudio-plugin-debuginfo': ['xfce4-mixer-debuginfo'],
    'xfig-debuginfo': ['transfig-debuginfo'],     # contain conflicting files
}

# provides: which don't exist
nonexistent_provides = [
    'perl5_026',
    'rdiff-debuginfo',           # not in x86
    'rxvt-unicode-X-debuginfo',  # not in x86_64
]

# empty source packages
#
# (these usually have a corresponding hand-built empty install package, which
# depends on it's replacement, and so are a lingering remnant of something not
# properly obsoleted)
empty_source = {
    'SuiteSparse-src': ['4.0.2-1'],
    'ash-src': ['20040127-5'],                   # obsoleted by dash
    'checkx-src': ['0.2.1-1'],                   # obsoleted by run2
    'db4.8-src': ['4.8.30-2'],                   # obsoleted by db
    'gcc-tools-autoconf-src': ['2.59-11'],       # obsoleted by gcc-tools-epoch{1,2}-autoconf
    'gcc-tools-automake-src': ['1.9.6-11'],      # obsoleted by gcc-tools-epoch{1,2}-automake
    'lzma-src': ['4.32.7-10'],                   # obsoleted by xz
    'mlcscope-src': ['99-1'],                    # obsoleted by cscope
    'octave-forge-src': ['20140215-1'],
    'octave-octcdf-src': ['1.1.7-99'],
    'perl-File-Slurp-Unicode-src': ['0.7.1-2'],  # obsoleted by perl-File-Slurp
    'pinentry-qt3-src': ['0.7.6-3'],             # obsoleted by pinentry-qt
    'xerces-c-devel-src': ['2.8.0-1'],           # obsoleted by libxerces-c-devel
}

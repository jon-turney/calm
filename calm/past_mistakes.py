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

# packages with historical versions containing a hyphen, or other illegal
# character
illegal_char_in_version = {
    'ctorrent': ['1.3.4-dnh3.2'],
    'email': ['3.2.1-git', '3.2.3-git'],
    'email-debuginfo': ['3.2.1-git', '3.2.3-git'],
    'fdupes': ['1.50-PR2'],
    'gendef': ['1.0-svn2931'],
    'gendef-debuginfo': ['1.0-svn2931'],
    'gt5': ['1.5.0~20111220+bzr29'],
    'hidapi': ['0.8.0-rc1'],
    'hidapi-debuginfo': ['0.8.0-rc1'],
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
}

# cygport places this into the requires of every debuginfo package, including
# cygwin-debuginfo itself
self_requires = [
    'cygwin-debuginfo'
]

# these are packages which only contain data, symlinks or scripts and thus
# function as their own source
self_source = [
    'R_autorebase',
    '_update-info-dir',
    'base-cygwin',
    'chere',
    'cygcheck-dep',
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
    'libfltk-doc',
    'libgcj-common',              # dropped from gcc 6
    'libical_cxx-devel',
    'libquota-devel',             # no longer provided by e2fsprogs
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
    'gcc-tools-epoch2-autoconf',
    'gcc-tools-epoch2-autoconf-src',
]

# packages with maintainer anomalies
#
# don't add to this list, fix the package
maint_anomalies = {
    'manlint': ['1.6g-2'],  # unclear why this is under man
    'python3-h5py-debuginfo': ['2.9.0-1'],  # superceded by python-h5py-debuginfo
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
    'procps-ng': ['procps'],
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
    '_windows',
    'perl5_026',
    'rdiff-debuginfo',
    'rxvt-unicode-X-debuginfo',
    'xfce4-mixer-debuginfo',
    'python3-dbus-debuginfo',
]

# provides: which don't exist and packages which require them should be expired
expired_provides = [
    'python26',
]

# empty source packages
#
# (these usually have a corresponding hand-built empty install package, which
# depends on it's replacement, and so are a lingering remnant of something not
# properly obsoleted)
empty_source = {
    'catgets-src': ['2.10.0-1'],
    'octave-octcdf-src': ['1.1.7-99'],
    'perl-File-Slurp-Unicode-src': ['0.7.1-2'],  # obsoleted by perl-File-Slurp
}

# additional data for the heuristic for upgrading old-style obsoletion packages
old_style_obsolete_by = {
    'at-spi2-atk': 'libatk-bridge2.0_0',
    'idle3': 'idle39',
    'lighttpd-mod_trigger_b4_dl': 'lighttpd',
    'qt-gstreamer': 'libQtGStreamer1_0_0',
    # these are odd and only exist to record an optional dependency on the
    # language runtime (dynamically loaded at runtime), which is also noted in
    # build-requires:
    'vim-lua': 'vim',
    'vim-perl': 'vim',
    'vim-python': 'vim',
    'vim-python3': 'vim',
    'vim-ruby': 'vim',
    # (An empty replacement means "don't apply this heuristic")
    # we have other plans for 'python3-*' packages, they will become virtuals
    'python3-.*': '',
    # these packages probably should be marked as self-destruct?
    'mate-utils': '',
    'texlive-collection-htmlxml': '',
    'w32api': '',
}

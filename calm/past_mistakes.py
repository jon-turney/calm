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
    'libmangle': ['1.0-svn2930'],
    'libmangle-debuginfo': ['1.0-svn2930'],
    'man-pages-posix': ['2013-a'],
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
    'mbedtls': ['2.16.0-1'],                               # useless empty package, not autosupressed as it has depends
}

# packages with maintainer anomalies
#
# don't add to this list, fix the package
maint_anomalies = {
    'manlint': ['1.6g-2'],  # unclear why this is under man
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

# historical provides
#
# something obsoletes these, but they were removed before we started remembering
# all historic_package_names
historical_provides = [
    'rdiff-debuginfo',
    'rxvt-unicode-X-debuginfo',
    'xfce4-mixer-debuginfo',
    'python3-dbus-debuginfo',
]

# provides: which don't exist
#
# we use regex patterns to match version provides which might have been expired,
# or not uploaded yet.
nonexistent_provides = historical_provides + [
    # python3
    'python35',
    'python35-gi',
    'glade3',
    # python2
    'python2',
    'python2-devel',
    'python27',
    'python27-.*',
    'python-appindicator',
    'python-gconf2',
    'python-gnome2',
    'python-gnomevfs2',
    'python-gtk2.0',
    'python-keybinder',
    'python-pynotify',
    'python-vte',
    'python-wnck',
    'python-zeitgeist',
    'python2-avahi',
    'python2-ayatana_appindicator',
    'python2-gobject',
    'python2-ipaddr',
    'python2-libvirt',
    'python2-matemenu',
    'python2-pykde4',
    'python2-pyqt4',
    'python2-pyqt5',
    'libtidy0_99_0',
    # general
    '_windows',
    r'perl5_\d+',
    r'ruby_\d+',
    r'tl_\d+',
    r'tl_basic_\d+',
]

# provides which don't exist, and were obsoleted by something else which we've
# forgotten about..
substitute_dependency = {
    'python-avahi': 'python2-avahi',
    'python-cairo': 'python27-cairo',
    'python-chardet': 'python27-chardet',
    'python-dbus': 'python27-dbus',
    'python-docutils': 'python27-docutils',
    'python-fontforge': 'python2-fontforge',
    'python-gi': 'python27-gi',
    'python-gobject': 'python2-gobject',
    'python-jinja2': 'python27-jinja2',
    'python-lxml': 'python27-lxml',
    'python-marisa': 'python27-marisa',
    'python-numpy': 'python27-numpy',
    'python-pygments': 'python27-pygments',
    'python-pykde4': 'python2-pykde4',
    'python-pyqt4': 'python2-pyqt4',
    'python-rdflib': 'python27-rdflib',
    'python-reportlab': 'python27-reportlab',
    'python-twisted': 'python27-twisted',
    'python-xdg': 'python27-xdg',
    'python2-clang': 'python27-clang',
    'python2-dbus': 'python27-dbus',
    'python2-future': 'python27-future',
    'python2-gi': 'python27-gi',
    'python2-gv': 'python27-gv',
    'python2-imaging': 'python27-imaging',
    'python2-ipython': 'python27-ipython',
    'python2-jinja2': 'python27-jinja2',
    'python2-libxml2': 'python27-libxml2',
    'python2-lxml': 'python27-lxml',
    'python2-nghttp2': 'python27-nghttp2',
    'python2-numpy': 'python27-numpy',
    'python2-requests': 'python27-requests',
    'python2-setuptools': 'python27-setuptools',
    'python2-six': 'python27-six',
    'python2-tkinter': 'python27-tkinter',
    'python2-wheel': 'python27-wheel',
    'python2-xdg': 'python27-xdg',
    'python2-yaml': 'python27-yaml',
}

# provides: which don't exist and packages which require them should be expired
expired_provides = [
    'python34',
    'python35',
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
    'octave-octcdf': 'octave-netcdf',
    'python-gi-common': 'python3-gi',
    'python-pyatspi-common': 'python3-pyatspi',
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
    'python-twisted-debuginfo': '',
    'vte2.91': '',
    # self-destruct, or need to start to exist
    'cron-debuginfo': '',
    'texlive-collection-htmlxml': '',
    'w32api': '',
}

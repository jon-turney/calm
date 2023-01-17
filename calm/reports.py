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

import io
import os
import re
import textwrap
import types

from . import common_constants
from . import maintainers
from . import package
from . import pkg2html
from . import utils
from .version import SetupVersion


def template(title, body, f):
    os.fchmod(f.fileno(), 0o755)

    print(textwrap.dedent('''\
    <!DOCTYPE html>
    <html>
    <head>
    <link rel="stylesheet" type="text/css" href="/style.css"/>
    <title>{0}</title>
    </head>
    <body>
    <div id="main">
    <h1>{0}</h1>''').format(title), file=f)

    print(body, file=f)

    print(textwrap.dedent('''\
    </div>
    </body>
    </html>'''), file=f)


def linkify(pn, po):
    return '<a href="/packages/summary/{0}.html">{1}</a>'.format(pn, po.orig_name)


#
# produce a report of unmaintained packages
#
def unmaintained(args, packages, reportsdir):
    pkg_maintainers = maintainers.pkg_list(args.pkglist)

    um_list = []

    arch = 'x86_64'
    # XXX: look into how we can make this 'src', after x86 is dropped
    for p in packages[arch]:
        po = packages[arch][p]

        if po.kind != package.Kind.source:
            continue

        if (po.orig_name not in pkg_maintainers) or (not pkg_maintainers[po.orig_name].is_orphaned()):
            continue

        # the highest version we have
        v = sorted(po.versions(), key=lambda v: SetupVersion(v), reverse=True)[0]

        # determine the number of unique rdepends over all subpackages (and
        # likewise build_rdepends)
        #
        # zero rdepends makes this package a candidate for removal, whereas lots
        # means it's important to update it.
        rdepends = set()
        build_rdepends = set()
        for subp in po.is_used_by:
            rdepends.update(packages[arch][subp].rdepends)
            build_rdepends.update(packages[arch][subp].build_rdepends)

        up = types.SimpleNamespace()
        up.pn = p
        up.po = po
        up.v = SetupVersion(v).V
        up.upstream_v = getattr(po, 'upstream_version', 'unknown')
        up.ts = po.tar(v).mtime
        up.rdepends = len(rdepends)
        up.build_rdepends = len(build_rdepends)

        # some packages are mature. If 'v' is still latest upstream version,
        # then maybe we don't need to worry about this package quite as much...
        up.unchanged = (SetupVersion(v)._V == SetupVersion(up.upstream_v)._V)
        if up.unchanged:
            up.upstream_v += " (unchanged)"

        um_list.append(up)

    body = io.StringIO()
    print('<p>Packages without a maintainer.</p>', file=body)

    print('<table class="grid">', file=body)
    print('<tr><th>last updated</th><th>package</th><th>version</th><th>upstream version</th><th>rdepends</th><th>build_rdepends</th></tr>', file=body)

    for up in sorted(um_list, key=lambda i: (i.rdepends + i.build_rdepends, not i.unchanged, i.ts), reverse=True):
        print('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
              (pkg2html.tsformat(up.ts), linkify(up.pn, up.po), up.v, up.upstream_v, up.rdepends, up.build_rdepends), file=body)

    print('</table>', file=body)

    unmaintained = os.path.join(reportsdir, 'unmaintained.html')
    with utils.open_amifc(unmaintained) as f:
        template('Unmaintained packages', body.getvalue(), f)


# produce a report of deprecated packages
#
def deprecated(args, packages, reportsdir):
    dep_list = []

    arch = 'x86_64'
    # XXX: look into how we can make this 'src', after x86 is dropped
    for p in packages[arch]:
        po = packages[arch][p]

        if po.kind != package.Kind.binary:
            continue

        if not re.match(common_constants.SOVERSION_PACKAGE_RE, p):
            continue

        if p.startswith('girepository-'):
            continue

        bv = po.best_version
        es = po.version_hints[bv].get('external-source', None)
        if not es:
            continue

        if packages[arch][es].best_version == bv:
            continue

        if po.tar(bv).is_empty:
            continue

        # an old version of a shared library
        depp = types.SimpleNamespace()
        depp.pn = p
        depp.po = po
        depp.v = bv
        depp.ts = po.tar(bv).mtime
        # number of rdepends which have a different source package
        depp.rdepends = len(list(p for p in po.rdepends if packages[arch][p].srcpackage(packages[arch][p].best_version) != es))

        dep_list.append(depp)

    body = io.StringIO()
    print(textwrap.dedent('''\
    <p>Packages for old soversions. (The corresponding source package produces a
    newer soversion, or has stopped producing this solib).</p>'''), file=body)

    print('<table class="grid">', file=body)
    print('<tr><th>package</th><th>version</th><th>timestamp</th><th>rdepends</th></tr>', file=body)

    for depp in sorted(dep_list, key=lambda i: (i.rdepends, i.ts), reverse=True):
        print('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
              (linkify(depp.pn, depp.po), depp.v, pkg2html.tsformat(depp.ts), depp.rdepends), file=body)

    print('</table>', file=body)

    deprecated = os.path.join(reportsdir, 'deprecated_so.html')
    with utils.open_amifc(deprecated) as f:
        template('Deprecated shared library packages', body.getvalue(), f)


#
def do_reports(args, packages):
    if args.dryrun:
        return

    reportsdir = os.path.join(args.htdocs, 'reports')
    pkg2html.ensure_dir_exists(args, reportsdir)

    unmaintained(args, packages, reportsdir)
    deprecated(args, packages, reportsdir)

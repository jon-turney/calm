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
    <script src="sorttable.js"></script>
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


def write_report(args, title, body, fn, reportlist, not_empty=True):
    if not_empty:
        reportlist[title] = os.path.join('reports', fn)

    fn = os.path.join(args.htdocs, 'reports', fn)

    with utils.open_amifc(fn) as f:
        template(title, body.getvalue(), f)


def linkify(pn, po):
    return '<a href="/packages/summary/{0}.html">{1}</a>'.format(po.name, po.orig_name)


#
# produce a report of unmaintained packages
#
def unmaintained(args, packages, reportlist):
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
        up.importance = po.importance

        # some packages are mature. If 'v' is still latest upstream version,
        # then maybe we don't need to worry about this package quite as much...
        up.unchanged = (SetupVersion(v)._V == SetupVersion(up.upstream_v)._V)
        if up.unchanged:
            up.upstream_v += " (unchanged)"

        um_list.append(up)

    body = io.StringIO()
    print('<p>Packages without a maintainer.</p>', file=body)

    print('<table class="grid sortable">', file=body)
    print('<tr><th>last updated</th><th>package</th><th>version</th><th>upstream version</th><th>rdepends</th><th>build_rdepends</th><th>importance</th></tr>', file=body)

    for up in sorted(um_list, key=lambda i: (-i.importance, i.rdepends + i.build_rdepends, not i.unchanged, i.ts), reverse=True):
        print('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
              (pkg2html.tsformat(up.ts), linkify(up.pn, up.po), up.v, up.upstream_v, up.rdepends, up.build_rdepends, up.importance), file=body)

    print('</table>', file=body)

    write_report(args, 'Unmaintained packages', body, 'unmaintained.html', reportlist)


# produce a report of deprecated packages
#
def deprecated(args, packages, reportlist):
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

        # filter rdepends
        depp.rdepends = []
        for d in po.rdepends:
            # have a different source package
            bv = packages[arch][d].best_version
            if packages[arch][d].srcpackage(bv) == es:
                continue

            # current version has the dependency of interest
            dpl = package.deplist_without_versions(packages[arch][d].version_hints[bv]['depends'])
            if p not in dpl:
                continue

            depp.rdepends.append(d)

        dep_list.append(depp)

    # produce a rebuild report for each solib
    for depp in dep_list:
        if len(depp.rdepends) == 0:
            continue

        body = io.StringIO()
        print('<p>Packages needing a rebuild for a later version solib than %s.</p>' % depp.pn, file=body)

        print('<table class="grid sortable">', file=body)
        print('<tr><th>package</th><th>srcpackage</th><th>version</th><th>timestamp</th></tr>', file=body)

        for r in sorted(depp.rdepends):
            po = packages[arch][r]
            bv = po.best_version
            spn = po.srcpackage(bv)
            spo = packages[arch][spn]

            print('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
                  (linkify(r, po), linkify(spn, spo), bv, pkg2html.tsformat(po.tar(bv).mtime)), file=body)

        print('</table>', file=body)

        write_report(args, 'Package needing rebuilds (%s)' % depp.pn, body, 'so_rebuild_%s.html' % depp.pn, reportlist, not_empty=False)

    # then produce an overall report
    body = io.StringIO()
    print(textwrap.dedent('''\
    <p>Packages for old soversions. (The corresponding source package produces a
    newer soversion, or has stopped producing this solib).</p>'''), file=body)

    print('<table class="grid sortable">', file=body)
    print('<tr><th>package</th><th>version</th><th>timestamp</th><th>rdepends</th></tr>', file=body)

    for depp in sorted(dep_list, key=lambda i: (len(i.rdepends), i.ts), reverse=True):
        len_link = len(depp.rdepends)
        if len_link:
            len_link = '<a href="so_rebuild_%s.html">%s</a>' % (depp.pn, len_link)

        print('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
              (linkify(depp.pn, depp.po), depp.v, pkg2html.tsformat(depp.ts), len_link), file=body)

    print('</table>', file=body)

    write_report(args, 'Deprecated shared library packages', body, 'deprecated_so.html', reportlist)


#
# produce a report of packages where the latest version is marked test: and has
# possibly been forgotten about
#
def unstable(args, packages, reportlist):
    unstable_list = []

    arch = 'x86_64'
    # XXX: look into how we can make this 'src', after x86 is dropped
    for p in packages[arch]:
        po = packages[arch][p]

        if po.kind != package.Kind.source:
            continue

        latest_v = sorted(po.versions(), key=lambda v: SetupVersion(v), reverse=True)[0]
        if 'test' not in po.version_hints[latest_v]:
            continue

        unstablep = types.SimpleNamespace()
        unstablep.pn = p
        unstablep.po = po
        unstablep.v = latest_v
        unstablep.ts = po.tar(latest_v).mtime

        unstable_list.append(unstablep)

    body = io.StringIO()
    print(textwrap.dedent('''\
    <p>Packages where latest version is marked as unstable (testing).</p>'''), file=body)

    print('<table class="grid sortable">', file=body)
    print('<tr><th>package</th><th>version</th><th>timestamp</th></tr>', file=body)

    for unstablep in sorted(unstable_list, key=lambda i: i.ts):
        print('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' %
              (linkify(unstablep.pn, unstablep.po), unstablep.v, pkg2html.tsformat(unstablep.ts)), file=body)

    print('</table>', file=body)

    write_report(args, 'Packages marked as unstable', body, 'unstable.html', reportlist)


# gather data on maintainer activity
#
def maintainer_activity(args, packages):
    activity_list = []

    arch = 'x86_64'
    # XXX: look into how we can make this 'src', after x86 is dropped

    ml = maintainers.maintainer_list(args)
    for m in ml.values():
        if m.name == 'ORPHANED':
            continue

        a = types.SimpleNamespace()
        a.name = m.name
        a.email = m.email
        a.last_seen = m.last_seen

        # because last_seen hasn't been collected for very long, we also try to
        # estimate last activity by looking at packages
        count = 0
        mtime = 0
        pkgs = []
        for p in m.pkgs:
            if not p.is_orphaned():
                count += 1

            pn = p.data + '-src'
            # do something reasonable for sourceless packages
            if pn not in packages[arch]:
                pn = p.data

            po = packages[arch].get(pn, None)
            if po:
                pkgs.append(pn)

                # ignore timestamp of co-maintained packages, because we don't
                # know who is responsible for the update
                if len(p.maintainers()) > 1:
                    continue

                for v in po.versions():
                    if po.tar(v).mtime > mtime:
                        mtime = po.tar(v).mtime

        # ignore if all their packages are orphaned
        # (key should be already disabled in this case)
        if count == 0:
            continue

        a.pkgs = pkgs
        a.last_package = mtime

        activity_list.append(a)

    return activity_list


# produce a report on maintainer (in)activity
#
def maintainer_activity_report(args, packages, reportlist):
    arch = 'x86_64'
    activity_list = maintainer_activity(args, packages)

    body = io.StringIO()
    print('<p>Maintainer activity.</p>', file=body)

    print('<table class="grid sortable">', file=body)
    print('<tr><th>Maintainer</th><th># packages</th><th>Last ssh</th><th>Latest package</th></tr>', file=body)

    for a in sorted(activity_list, key=lambda i: max(i.last_seen, i.last_package)):
        def pkg_details(pkgs):
            return '<details><summary>%d</summary>%s</details>' % (len(pkgs), ', '.join(linkify(p, packages[arch][p]) for p in pkgs))

        print('<tr><td>%s</td><td sorttable_customkey="%d">%s</td><td>%s</td><td>%s</td></tr>' %
              (a.name, len(a.pkgs), pkg_details(a.pkgs), pkg2html.tsformat(a.last_seen), pkg2html.tsformat(a.last_package)), file=body)

    print('</table>', file=body)

    write_report(args, 'Maintainer activity', body, 'maintainer_activity.html', reportlist, not_empty=False)


# produce a report of packages which need rebuilding for the latest major
# version version provides
#
def provides_rebuild(args, packages, fn, provide_package, reportlist):
    pr_list = []

    arch = 'x86_64'
    # XXX: look into how we can change this, after x86 is dropped

    pp_package = packages[arch].get(provide_package, None)
    pp_provide = None

    if pp_package:
        pp_bv = pp_package.best_version
        pp_provide = pp_package.version_hints[pp_bv]['provides'][0]
        pp_provide_base = re.sub(r'\d+$', '', pp_provide)

        for p in packages[arch]:
            po = packages[arch][p]
            bv = po.best_version

            depends = packages[arch][p].version_hints[bv]['depends']
            depends = package.deplist_without_versions(depends)

            for d in depends:
                if not d.startswith(pp_provide_base):
                    continue

                if d == pp_provide:
                    continue

                if po.obsoleted_by:
                    continue

                # requires an old provide
                pr = types.SimpleNamespace()
                pr.pn = p
                pr.po = po
                pr.spn = po.srcpackage(bv)
                pr.spo = packages[arch][pr.spn]
                pr.depends = d
                pr.bv = bv

                pr_list.append(pr)
                break

    body = io.StringIO()
    print('<p>Packages whose latest version depends on a version provides: other than %s.</p>' % pp_provide, file=body)

    print('<table class="grid sortable">', file=body)
    print('<tr><th>package</th><th>srcpackage</th><th>version</th><th>depends</th></tr>', file=body)

    for pr in sorted(pr_list, key=lambda i: (i.depends, i.pn)):
        print('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
              (linkify(pr.pn, pr.po), linkify(pr.spn, pr.spo), pr.bv, pr.depends), file=body)

    print('</table>', file=body)

    write_report(args, 'Packages needing rebuilds for latest %s' % provide_package, body, fn, reportlist, bool(pr_list))


# produce a report of python modules/bindings/linked packages which depend on
# non-latest version of python
def python_rebuild(args, packages, fn, reportlist):
    pr_list = []

    # XXX: look into how we can change this, after x86 is dropped
    arch = 'x86_64'

    # assume that python3 depends only on the latest python3n package
    py_package = packages[arch].get('python3', None)
    if not py_package:
        return

    latest_py = py_package.version_hints[py_package.best_version]['depends'][0]

    modules = {}

    for p in packages[arch]:
        po = packages[arch][p]
        bv = po.best_version

        if po.obsoleted_by:
            continue

        depends = packages[arch][p].version_hints[bv]['depends']
        depends = package.deplist_without_versions(depends)

        for d in depends:
            # scan for a 'pythonnn' dependency
            if not re.match(r'python\d+$', d):
                continue

            # if it's a generic python dependency, it's ok
            if d == 'python3':
                continue

            # if this package is called 'idlenn', it's ok
            if p == d.replace('python', 'idle'):
                break

            # if this package is called 'pythonnn-foo', it's ok, and remember
            # the module/binding name and version
            if p.startswith(d + '-'):
                name = p[len(d) + 1:]

                if name not in modules:
                    modules[name] = []

                ver = int(d[6:])
                modules[name].append(ver)

                break

            # if it depends on the latest python version, this package is ok
            if d == latest_py:
                break

            # requires an old python version
            pr = types.SimpleNamespace()
            pr.pn = p
            pr.po = po
            pr.spn = po.srcpackage(bv)
            pr.spo = packages[arch][pr.spn]
            pr.depends = d
            pr.bv = bv

            pr_list.append(pr)

            break

    # now look at list of module/bindings we've made
    latest_ver = int(latest_py[6:])
    for m in modules:
        highest_ver = sorted(modules[m], reverse=True)[0]
        if highest_ver == latest_ver:
            continue

        # if module/binding doesn't exist for latest python version, indicate
        # that it needs updating
        pr = types.SimpleNamespace()
        pr.pn = 'python' + str(highest_ver) + '-' + m
        pr.po = packages[arch][pr.pn]
        pr.spn = pr.po.srcpackage(pr.po.best_version)
        pr.spo = packages[arch][pr.spn]
        pr.depends = 'python' + str(highest_ver)
        pr.bv = pr.po.best_version

        pr_list.append(pr)

    body = io.StringIO()
    print('<p>Packages for python module or binding for, or linkage to, a python version other than %s.</p>' % latest_py, file=body)

    print('<table class="grid sortable">', file=body)
    print('<tr><th>package</th><th>srcpackage</th><th>version</th><th>depends</th></tr>', file=body)

    for pr in sorted(pr_list, key=lambda i: (i.depends, i.pn)):
        print('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
              (linkify(pr.pn, pr.po), linkify(pr.spn, pr.spo), pr.bv, pr.depends), file=body)

    print('</table>', file=body)

    write_report(args, 'Packages needing rebuilds for latest python', body, fn, reportlist, bool(pr_list))


#
def do_reports(args, packages):
    if args.dryrun:
        return

    reportlist = {}

    pkg2html.ensure_dir_exists(args, os.path.join(args.htdocs, 'reports'))

    unmaintained(args, packages, reportlist)
    deprecated(args, packages, reportlist)
    unstable(args, packages, reportlist)

    provides_rebuild(args, packages, 'perl_rebuilds.html', 'perl_base', reportlist)
    provides_rebuild(args, packages, 'ruby_rebuilds.html', 'ruby', reportlist)
    python_rebuild(args, packages, 'python_rebuilds.html', reportlist)

    maintainer_activity_report(args, packages, reportlist)

    fn = os.path.join(args.htdocs, 'reports_list.inc')
    with utils.open_amifc(fn) as f:
        print('<ul>', file=f)
        for r in reportlist:
            print('<li>', file=f)
            print('<a href="%s">%s</a>' % (reportlist[r], r), file=f)
            print('</li>', file=f)
        print('</ul>', file=f)

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
# write package listing HTML files
#
# - build a list of all files under HTDOCS/packages/<arch>
# - for each package in the package database
# --- create a .htaccess file in the package directory, if not present
# -- for each tar file
# --- if a package listing HTML file doesn't already exist
# ---- write a HTML package listing file listing the tar file contents
# -- write a summary file (unless we don't think it's changed)
# - write packages.inc, the list of packages
# - remove any .htaccess or listing files for which there was no package
# - remove any directories which are now empty
#
# note that the directory hierarchy of (noarch|arch)/package/subpackages is
# flattened in the package listing to just the package name
#

import argparse
import functools
import glob
import html
import logging
import lzma
import math
import os
import re
import string
import sys
import tarfile
import textwrap
import time
import types
from typing import NamedTuple

import markdown

import xtarfile

from . import common_constants
from . import maintainers
from . import package
from . import reports
from . import utils
from .version import SetupVersion


summary_last_touched = {}
SUMMARY_REWRITE_INTERVAL = (24 * 60 * 60)


#
# get sdesc for a package
#
def sdesc(po, bv):
    header = po.version_hints[bv]['sdesc']
    header = header.strip('"')
    return html.escape(header, quote=False)


#
# ditto for ldesc
#
def ldesc(po, bv):
    if 'ldesc' in po.version_hints[bv]:
        header = po.version_hints[bv]['ldesc']
    else:
        return sdesc(po, bv)

    header = header.strip('"')
    header = markdown.markdown(header)

    # linkify things which look like URLs
    def linkify_without_fullstop(m):
        url = m.group(0)
        suffix = ''
        if url[-1] == '.':
            suffix = url[-1]
            url = url[0:-1]
        return '<a href="{0}">{0}</a>{1}'.format(url, suffix)

    header = re.sub(r'http(s|)://[\w./_-]*', linkify_without_fullstop, header)

    return header


#
# ensure a directory exists
#
def ensure_dir_exists(args, path):
    if not args.dryrun:
        utils.makedirs(path)
        try:
            os.chmod(path, 0o755)
        except PermissionError:
            pass


#
# format a unix epoch time (UTC)
#
def tsformat(ts):
    if ts == 0:
        return 'Unknown'
    else:
        return time.strftime('%Y-%m-%d %H:%M', time.gmtime(ts))


#
#
#

def update_package_listings(args, packages):
    update_summary = set()
    update_summary.update(write_package_listings(args, packages))

    summaries = os.path.join(args.htdocs, 'summary')
    ensure_dir_exists(args, summaries)

    pkg_maintainers = maintainers.pkg_list(args.pkglist)

    toremove = glob.glob(os.path.join(summaries, '*'))

    def linkify_package(pkg):
        p = re.sub(r'(.*)\s+\(.*\)', r'\1', pkg)
        if p in packages:
            pn = packages[p].orig_name
            text = re.sub(re.escape(p), pn, pkg)
            return '<a href="%s.html">%s</a>' % (p, text)
        logging.debug('package linkification failed for %s' % p)
        return p

    now = time.time()

    for p in packages:
        #
        # write package summary
        #
        # (these exist in a separate directory to prevent their contents being
        # searched by the package search script)
        #
        summary = os.path.join(summaries, p + '.html')

        # this file should exist, so remove from the toremove list
        if summary in toremove:
            toremove.remove(summary)

        po = packages[p]
        bv = po.best_version

        # update summary if:
        # - it doesn't already exist,
        # - or, listing files (i.e packages versions) were added or removed,
        # - or, hints have changed since it was written
        # - or, SUMMARY_REWRITE_INTERVAL has elapsed since it was last written
        # - or, forced
        hint_mtime = po.hints[bv].mtime

        summary_mtime = 0
        if os.path.exists(summary):
            summary_mtime = os.path.getmtime(summary)

        if (p in update_summary) or (summary_mtime < hint_mtime) or (now > summary_last_touched.get(p, 0) + SUMMARY_REWRITE_INTERVAL) or args.force:
            if not args.dryrun:
                summary_last_touched[p] = now
                with utils.open_amifc(summary) as f:
                    os.fchmod(f.fileno(), 0o755)

                    if po.kind == package.Kind.source:
                        pn = po.orig_name
                        title = "Cygwin Package Summary for %s (source)" % pn
                        kind = "Source Package"
                    else:
                        pn = p
                        title = "Cygwin Package Summary for %s" % p
                        kind = "Package"

                    print(textwrap.dedent('''\
                    <!DOCTYPE html>
                    <html>
                    <head>
                    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
                    <link rel="stylesheet" type="text/css" href="../../style.css"/>
                    <title>%s</title>
                    </head>
                    <body>
                    <!--#include virtual="/navbar.html" -->
                    <div id="main">
                    <!--#include virtual="/top.html" -->
                    <h1>%s: %s</h1>''' % (title, kind, pn)), file=f)

                    details_table = {}
                    details_table['summary'] = sdesc(po, bv)
                    details_table['description'] = ldesc(po, bv)
                    details_table['categories'] = po.version_hints[bv].get('category', '')

                    class PackageData(NamedTuple):
                        is_attr: bool = False
                        summarize_limit: int = 0

                    if po.kind == package.Kind.source:
                        details = {'build-depends': PackageData()}
                    else:
                        details = {
                            'depends': PackageData(),
                            'obsoletes': PackageData(),
                            'obsoleted_by': PackageData(is_attr=True),
                            'provides': PackageData(),
                            'conflicts': PackageData(),
                            'rdepends': PackageData(is_attr=True, summarize_limit=10),
                            'build_rdepends': PackageData(is_attr=True, summarize_limit=10)
                        }

                    for key in details:
                        # XXX: multiarch TODO:
                        # access to per-arch version_hints ???
                        pos = {}
                        for arch in common_constants.ARCHES:
                            pos[arch] = po

                        # make the union of the package list for this detail
                        # across arches, and then annotate any items which don't
                        # appear for all arches
                        value = {}
                        values = set()
                        for arch in pos:
                            if details[key].is_attr:
                                value[arch] = getattr(pos[arch], key, set())
                            else:
                                t = pos[arch].version_hints[pos[arch].best_version].get(key, [])
                                value[arch] = set(t)
                            values.update(value[arch])

                        if values:
                            detail = []
                            for detail_pkg in sorted(values):
                                if all(detail_pkg in value[arch] for arch in pos):
                                    detail.append(linkify_package(detail_pkg))
                                else:
                                    detail.append(linkify_package(detail_pkg) + ' (%s)' % (','.join([arch for arch in pos if detail_pkg in value[arch]])))

                            limit = details[key].summarize_limit
                            if limit and len(detail) > limit:
                                details_table[key] = '<details><summary>(%s)</summary>%s</details>' % (len(detail), ', '.join(detail))
                            else:
                                details_table[key] = ', '.join(detail)

                    if po.kind == package.Kind.source:
                        es = p

                        install_packages = po.is_used_by
                        details_table['install package(s)'] = ', '.join([linkify_package(p) for p in sorted(install_packages)])

                        homepage = po.version_hints[po.best_version].get('homepage', None)
                        if homepage:
                            details_table['homepage'] = '<a href="%s">%s</a>' % (homepage, homepage)

                        lic = po.version_hints[po.best_version].get('license', None)
                        if lic:
                            details_table['license'] = '%s <span class="smaller">(<a href="https://spdx.org/licenses/">SPDX</a>)</span>' % (lic)
                    else:
                        es = po.srcpackage(bv)
                        details_table['source package'] = linkify_package(es)

                    if es in packages:
                        es_po = packages[es]
                    else:
                        es_po = po

                    m_pn = es_po.orig_name
                    if m_pn not in pkg_maintainers:
                        m = None
                        pkg_groups = None
                    else:
                        if pkg_maintainers[m_pn].is_orphaned():
                            m = 'ORPHANED'
                        else:
                            m = ', '.join('<a href="../reports/%s">%s</a>' % (reports.filenameify(l), l) for l in sorted(pkg_maintainers[m_pn].maintainers()))

                        pkg_groups = pkg_maintainers[m_pn].groups()

                    if m:
                        details_table['maintainer(s)'] = m + textwrap.dedent('''
                        <span class="smaller">(Use <a href="/lists.html#cygwin">the mailing list</a> to report bugs or ask questions.
                        <a href="/problems.html#personal-email">Do not contact the maintainer(s) directly</a>.)</span>''')

                    if pkg_groups:
                        details_table['groups'] = ','.join(pkg_groups)

                    if po.kind == package.Kind.source:
                        if args.repodir:
                            repo = os.path.join(args.repodir, '%s.git' % pn)
                            if os.path.exists(repo):
                                repo_browse_url = '/cgit/cygwin-packages/%s/' % pn
                                details_table['packaging repository'] = '<a href="%s">%s.git</a>' % (repo_browse_url, pn)

                        repology_pn = getattr(po, 'repology_project_name', None)
                        if repology_pn:
                            upstream_version = getattr(po, 'upstream_version', None)
                            if isinstance(upstream_version, str):
                                upstream_version = '(%s)' % upstream_version
                            else:
                                upstream_version = ''

                            details_table['repology info'] = '<a href="https://repology.org/project/%s/information">%s</a> %s' % (repology_pn, repology_pn, upstream_version)

                    if po.kind == package.Kind.binary:
                        doc_path = os.path.join(args.htdocs, 'doc', pn)
                        if os.path.exists(doc_path):
                            links = []

                            for readme in sorted(os.listdir(doc_path)):
                                links.append('<a href="../doc/%s/%s">%s</a>' % (pn, readme, readme))

                            details_table['readme'] = ', '.join(links)

                    # output details table
                    print('<table class="pkgdetails">', file=f)
                    for d, v in details_table.items():
                        if not v.startswith('<p>'):
                            v = '<p>' + v + '</p>'
                        print('<tr><td><p><span class="detail">%s</span>:</p></td><td>%s</td></tr>' % (d, v), file=f)
                    print('</table><br>', file=f)

                    # output package versions table
                    versions_table = []

                    def tar_line(pn, p, v):
                        item = types.SimpleNamespace()
                        item.version = v
                        item.size = int(math.ceil(p.tar(v).size / 1024))
                        if p.kind == package.Kind.binary:
                            target = "%s-%s" % (p.orig_name, v)
                        else:
                            target = "%s-%s-src" % (p.orig_name, v)
                        item.link = "../%s/%s/%s" % (p.tar(v).arch, pn, target)
                        item.status = 'test' if 'test' in p.version_hints[v] else 'stable'
                        item.ts = tsformat(p.tar(v).mtime)
                        item.arch = p.tar(v).arch
                        return item

                    # XXX: multiarch TODO: iterate over all versions and arches per version?
                    for version in packages[p].versions():
                        versions_table.append(tar_line(p, packages[p], version))

                    print('<table class="pkgtable">', file=f)
                    print('<tr><th>Version</th><th>Arch</th><th>Package Size</th><th>Date</th><th>Files</th><th>Status</th></tr>', file=f)
                    for i in sorted(versions_table, key=lambda i: (SetupVersion(i.version), i.arch)):
                        print('<tr><td>%s</td><td>%s</td><td class="right">%d KiB</td><td>%s</td><td>[<a href="%s">list of files</a>]</td><td>%s</td></tr>' % (i.version, i.arch, i.size, i.ts, i.link, i.status), file=f)
                    print('</table><br>', file=f)

                    print(textwrap.dedent('''\
                    </div>
                    </body>
                    </html>'''), file=f)

    for r in toremove:
        logging.debug('rm %s' % r)
        if not args.dryrun:
            os.unlink(r)

    write_packages_inc(args, packages, 'packages.inc', package.Kind.binary, 'package_list.html')
    write_packages_inc(args, packages, 'src_packages.inc', package.Kind.source, 'src_package_list.html')


# callback function for open_amifc to touch including file
def touch_including(including_file, changed):
    if changed:
        # touch the including file for the benefit of 'XBitHack full'
        if os.path.exists(including_file):
            logging.info("touching %s for the benefit of 'XBitHack full'" % (including_file))
            utils.touch(including_file)


#
# write package index page fragment for inclusion
#
def write_packages_inc(args, packages, name, kind, includer):
    packages_inc = os.path.join(args.htdocs, name)
    if not args.dryrun:
        package_list = os.path.join(args.htdocs, includer)
        with utils.open_amifc(packages_inc, cb=functools.partial(touch_including, package_list)) as index:
            os.fchmod(index.fileno(), 0o644)

            # Install package list contains all packages in any arch.
            # Source package list appear under their original package name.
            package_list = {}
            for p in packages:
                if p.endswith('-debuginfo'):
                    continue

                if packages[p].not_for_output:
                    continue

                if packages[p].kind == kind:
                    package_list[packages[p].orig_name] = p

            jumplist = set()
            for k in package_list:
                p = package_list[k]
                c = p[0].lower()
                if c in string.ascii_lowercase:
                    jumplist.add(c)

            print('<p class="center">', file=index)
            print('%d packages : ' % len(package_list), file=index)
            print(' - \n'.join(['<a href="#%s">%s</a>' % (c, c) for c in sorted(jumplist)]), file=index)
            print('</p>', file=index)

            print('<table class="pkglist">', file=index)

            first = ' class="pkgname"'
            jump = ''
            for k in sorted(package_list, key=package.sort_key):
                p = package_list[k]

                if p not in packages:
                    continue

                po = packages[p]

                bv = po.best_version
                header = sdesc(po, bv)

                if po.kind == package.Kind.source:
                    pn = po.orig_name
                    if 'source' not in header:
                        header += ' (source)'
                else:
                    pn = p

                anchor = ''
                if jump != p[0].lower():
                    jump = p[0].lower()
                    if jump in jumplist:
                        anchor = ' id="%s"' % (jump)

                print('<tr%s><td%s><a href="summary/%s.html">%s</a></td><td>%s</td></tr>' %
                      (anchor, first, p, pn, header),
                      file=index)
                first = ''

            print('</table>', file=index)


#
# write package doc catalogue fragment for inclusion
#
doc_inc_overrides = {'X': 'https://x.cygwin.com/'}


def write_doc_inc(args):
    packages_inc = os.path.join(args.htdocs, 'packages_docs.inc')
    if not args.dryrun:
        htaccess = os.path.join(args.htdocs, 'doc', '.htaccess')
        if not os.path.exists(htaccess) or args.force:
            with utils.open_amifc(htaccess) as f:
                # README files are text
                print('AddType text/plain README', file=f)

        package_docs = os.path.join(args.htdocs, 'package_docs.html')
        with utils.open_amifc(packages_inc, cb=functools.partial(touch_including, package_docs)) as index:
            os.fchmod(index.fileno(), 0o644)

            print('<div class="multicolumn-list">', file=index)

            dir_list = os.listdir(os.path.join(args.htdocs, 'doc'))

            for d in sorted(set(dir_list).union(doc_inc_overrides.keys()), key=package.sort_key):
                if d.startswith('.'):
                    continue

                if d in doc_inc_overrides:
                    print('<p><a href="%s">%s</a></p>' % (doc_inc_overrides[d], d),
                          file=index)
                else:
                    links = []
                    different_name = False

                    for f in sorted(os.listdir(os.path.join(args.htdocs, 'doc', d))):
                        links.append('<a href="doc/%s/%s">%s</a>' % (d, f, f.replace('.README', '')))

                        if f.replace('.README', '') != d:
                            different_name = True

                    if (len(links) > 1) or different_name:
                        print('<p>%s: %s</p>' % (d, ', '.join(links)), file=index)
                    elif links:
                        print('<p>%s</p>' % (', '.join(links)), file=index)

            print('</div>', file=index)


def write_package_listings(args, packages):
    update_summary = set()
    update_doc_inc = False

    # collect together a list of all the listing files
    #
    # (this has to be done at this level, since we want to remove listings
    # corresponding to removed packages)
    toremove = set()

    #
    # write base directory .htaccess, if needed
    #
    # force trying to access the base directory to redirect to the package list
    # page (as having the server index this directory containing lots of
    # subdirectories makes this URL very expensive to serve if someone stumbles
    # onto it by accident)
    #
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        base = os.path.join(args.htdocs, arch)
        ensure_dir_exists(args, base)

        htaccess = os.path.join(base, '.htaccess')
        if not os.path.exists(htaccess) or args.force:
            if not args.dryrun:
                with utils.open_amifc(htaccess) as f:

                    print('Redirect temp /packages/%s/index.html https://cygwin.com/packages/package_list.html' % (arch),
                          file=f)

        toremove.update(glob.glob(os.path.join(base, '*', '*')))
        toremove.update(glob.glob(os.path.join(base, '*', '.*')))

    for p in packages:

        def check_directory_setup(dirpath):
            ensure_dir_exists(args, dirpath)

            #
            # write .htaccess if needed
            #
            htaccess = os.path.join(dirpath, '.htaccess')
            if not os.path.exists(htaccess):
                if not args.dryrun or args.force:
                    with utils.open_amifc(htaccess) as f:
                        # We used to allow access to the directory listing as a
                        # crude way of listing the versions of the package available
                        # for which file lists were available. Redirect that index
                        # page to the summary page, which now has that information
                        # (and more).
                        print('RedirectMatch temp /packages/%s/%s/$ /packages/summary/%s.html' % (arch, p, p),
                              file=f)

                        # listing files don't have the extension, but are html
                        print('ForceType text/html', file=f)

            # this file should exist, so remove from the toremove list
            if htaccess in toremove:
                toremove.remove(htaccess)

        #
        # for each tarfile, write tarfile listing
        #

        # XXX: multiarch TODO: iterate over all versions and arches per version?
        for v in sorted(packages[p].versions(), key=lambda v: SetupVersion(v)):
            to = packages[p].tar(v)

            dirpath = os.path.join(args.htdocs, to.arch, p)
            # the way this filename is built is pretty arbitrary, but is linked
            # to from the summary page, and package-grep relies on its knowledge
            # of the scheme when producing its output
            fn = packages[p].orig_name + '-' + v + ('-src' if packages[p].kind == package.Kind.source else '')
            listing = os.path.join(dirpath, fn)

            check_directory_setup(dirpath)

            # ... if it doesn't already exist, or --force --force
            if not os.path.exists(listing) or (args.force > 1):

                if not args.dryrun:
                    # versions are being added, so summary needs updating
                    update_summary.add(p)

                    with utils.open_amifc(listing) as f:
                        bv = packages[p].best_version
                        desc = sdesc(packages[p], bv)

                        if packages[p].kind == package.Kind.source:
                            desc = desc + " (source)"

                        print(textwrap.dedent('''\
                                                 <!DOCTYPE html>
                                                 <html>
                                                 <head>
                                                 <title>%s: %s</title>
                                                 </head>
                                                 <body>
                                                 <h1><a href="/packages/summary/%s.html">%s</a>: %s</h1>
                                                 <pre>''' % (p, desc, p, p, desc)), file=f)

                        tf = to.repopath.abspath(args.rel_area)
                        if not os.path.exists(tf):
                            # this shouldn't happen with a full mirror
                            logging.error("tarfile %s not found" % (tf))
                        elif os.path.getsize(tf) <= 32:
                            # compressed empty files aren't a valid tar file,
                            # but we can just ignore them
                            pass
                        else:
                            try:
                                with xtarfile.open(tf, mode='r') as a:
                                    for i in a:
                                        print('    %-16s%12d %s' % (time.strftime('%Y-%m-%d %H:%M', time.gmtime(i.mtime)), i.size, i.name), file=f, end='')
                                        if i.isdir():
                                            print('/', file=f, end='')
                                        if i.issym() or i.islnk():
                                            print(' -> %s' % i.linkname, file=f, end='')
                                        print('', file=f)

                                        # extract Cygwin-specific READMEs
                                        if i.name.startswith('usr/share/doc/Cygwin/') and i.name.endswith('README'):
                                            logging.info("extracting %s to cygwin-specific documents directory" % (i.name))

                                            readme_text = a.extractfile(i).read()
                                            # redact email addresses
                                            readme_text = re.sub(rb'<(.*)@(.*)>', rb'<\1 at \2>', readme_text)

                                            doc_dir = os.path.join(args.htdocs, 'doc', p)
                                            ensure_dir_exists(args, doc_dir)

                                            # accommodate an historical error where the README was installed as
                                            # $PN-$PV.README, by stripping off any version suffix after the
                                            # package name
                                            basename = re.sub(r'(.*)-[.0-9ga]*.README', r'\1.README', os.path.basename(i.name))

                                            with open(os.path.join(doc_dir, basename), mode='wb') as readme:
                                                readme.write(readme_text)

                                            update_doc_inc = True

                            except (tarfile.TarError, lzma.LZMAError) as e:
                                print('package is corrupted', file=f)
                                logging.error("exception %s while reading %s" % (type(e).__name__, tf))
                                logging.debug('', exc_info=True)

                        print(textwrap.dedent('''\
                                                 </pre>
                                                 </body>
                                                 </html>'''), file=f)
            else:
                logging.log(5, 'not writing %s, already exists' % listing)

            # this file should exist, so remove from the toremove list
            if listing in toremove:
                toremove.remove(listing)

    #
    # remove any remaining files for which there was no corresponding package
    #
    for r in sorted(toremove):
        logging.debug('rm %s' % r)
        if not args.dryrun:
            # if we end up with '<arch>/packagename/someversion' left in the
            # toremove list, packagename needs a summary update
            p = r.split(os.path.sep)[1]
            update_summary.add(p)

            # remove the file
            os.unlink(r)

            # remove any directories which are now empty
            dirpath = os.path.dirname(r)
            if len(os.listdir(dirpath)) == 0:
                logging.debug('rmdir %s' % dirpath)
                os.rmdir(os.path.join(dirpath))

    # update the package documents list
    if update_doc_inc or args.force:
        write_doc_inc(args)

    return update_summary


if __name__ == "__main__":
    htdocs_default = os.path.join(common_constants.HTDOCS, 'packages')
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='Write HTML package listings')
    parser.add_argument('--force', action='store_true', help="overwrite existing files")
    parser.add_argument('--htdocs', action='store', metavar='DIR', help="htdocs output directory (default: " + htdocs_default + ")", default=htdocs_default)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    parser.add_argument('-n', '--dry-run', action='store_true', dest='dryrun', help="don't do anything")
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output')
    (args) = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    packages, _ = package.read_packages(args.rel_area)
    write_doc_inc(args)

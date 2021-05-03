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
# -- write a summary file, if set of versions changed
# - write packages.inc, the list of packages
# - remove any .htaccess or listing files for which there was no package
# - remove any directories which are now empty
#
# note that the directory hierarchy of (noarch|arch)/package/subpackages is
# flattened in the package listing to just the package name
#

import argparse
import glob
import html
import itertools
import logging
import math
import os
import re
import string
import sys
import textwrap
import time
import xtarfile

from .version import SetupVersion
from . import common_constants
from . import maintainers
from . import package
from . import utils


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
    # escape html entities
    header = html.escape(header, quote=False)
    header = header.replace('\n\n', '\n<br>\n')
    # try to recognize things which look like bullet points
    header = re.sub(r'\n(\s*[*-]\s)', r'<br>\n\1', header)
    # linkify things which look like hyperlinks
    header = re.sub(r'http(s|)://[^\s\)]*', r'<a href="\g<0>">\g<0></a>', header)

    return header


#
# try hard to find a package object for package p
#
def arch_package(packages, p):
    for arch in common_constants.ARCHES:
        if p in packages[arch]:
            return packages[arch][p]
    return None


#
# build a dict of the arches which contain package p
#
def arch_packages(packages, p):
    result = {}
    for arch in common_constants.ARCHES:
        if p in packages[arch]:
            result[arch] = packages[arch][p]
    return result


#
# ensure a directory exists
#
def ensure_dir_exists(args, path):
    if not args.dryrun:
        utils.makedirs(path)
        os.chmod(path, 0o755)


#
#
#

def update_package_listings(args, packages):
    package_list = set()
    update_summary = set()

    for arch in packages:
        update_summary.update(write_arch_listing(args, packages[arch], arch))
        package_list.update(packages[arch])

    summaries = os.path.join(args.htdocs, 'summary')
    ensure_dir_exists(args, summaries)

    mlist = maintainers.read(args, None)
    pkg_maintainers = maintainers.invert(mlist)

    toremove = glob.glob(os.path.join(summaries, '*'))

    def linkify_package(p):
        if p in package_list:
            pn = arch_package(packages, p).orig_name
            return '<a href="%s.html">%s</a>' % (p, pn)
        logging.debug('package linkification failed for %s' % p)
        return p

    for p in package_list:
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

        # if listing files were added or removed, or it doesn't already exist,
        # or force, update the summary
        if p in update_summary or not os.path.exists(summary) or args.force:
            if not args.dryrun:
                with utils.open_amifc(summary) as f:
                    os.fchmod(f.fileno(), 0o755)

                    pos = arch_packages(packages, p)
                    if not pos:
                        continue

                    po = next(iter(pos.values()))
                    bv = po.best_version

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

                    print('<span class="detail">summary</span>: %s<br><br>' % sdesc(po, bv), file=f)
                    print('<span class="detail">description</span>: %s<br><br>' % ldesc(po, bv), file=f)
                    print('<span class="detail">categories</span>: %s<br><br>' % po.version_hints[bv].get('category', ''), file=f)

                    if po.kind == package.Kind.source:
                        details = ['build-depends']
                    else:
                        details = ['depends', 'obsoletes', 'provides', 'conflicts']

                    for key in details:
                        # make the union of the package list for this detail
                        # across arches, and then annotate any items which don't
                        # appear for all arches
                        value = {}
                        values = set()
                        for arch in pos:
                            t = pos[arch].version_hints[pos[arch].best_version].get(key, None)
                            if t:
                                value[arch] = set(t.split(', '))
                            else:
                                value[arch] = set()
                            values.update(value[arch])

                        if values:
                            detail = []
                            for detail_pkg in sorted(values):
                                if all(detail_pkg in value[arch] for arch in pos):
                                    detail.append(linkify_package(detail_pkg))
                                else:
                                    detail.append(linkify_package(detail_pkg) + ' (%s)' % (','.join([arch for arch in pos if detail_pkg in value[arch]])))

                            print('<span class="detail">%s</span>: %s<br><br>' % (key, ', '.join(detail)), file=f)

                    if po.kind == package.Kind.source:
                        es = p
                        print('<span class="detail">install package(s)</span>: %s<br><br>' % ', '.join([linkify_package(p) for p in sorted(po.is_used_by)]), file=f)
                        homepage = po.version_hints[po.best_version].get('homepage', None)
                        if homepage:
                            print('<span class="detail">homepage</span>: <a href="%s">%s</a><br><br>' % (homepage, homepage), file=f)
                    else:
                        es = po.version_hints[bv].get('external-source', p + '-src')
                        print('<span class="detail">source package</span>: %s<br><br>' % linkify_package(es), file=f)

                    es_po = arch_package(packages, es)
                    if not es_po:
                        es_po = po
                    m_pn = es_po.orig_name
                    if 'ORPHANED' in pkg_maintainers[m_pn]:
                        m = 'ORPHANED'
                    else:
                        m = ', '.join(sorted(pkg_maintainers[m_pn]))

                    if m:
                        print('<span class="detail">maintainer(s)</span>: %s ' % m, file=f)

                        print(textwrap.dedent('''\
                        <span class="smaller">(Use <a href="/lists.html#cygwin">the mailing list</a> to report bugs or ask questions.
                        <a href="/problems.html#personal-email">Do not contact the maintainer(s) directly</a>.)</span>'''), file=f)
                        print('<br><br>', file=f)

                    print('<ul>', file=f)
                    for arch in sorted(packages):
                        if p in packages[arch]:

                            print('<li><span class="detail">%s</span></li>' % arch, file=f)

                            print('<table class="pkgtable">', file=f)
                            print('<tr><th>Version</th><th>Package Size</th><th>Date</th><th>Files</th><th>Status</th></tr>', file=f)

                            def tar_line(pn, p, category, v, arch, f):
                                if category not in p.vermap[v]:
                                    return
                                size = int(math.ceil(p.tar(v, category).size / 1024))
                                name = v if category == 'install' else v + ' (source)'
                                target = "%s-%s" % (p.orig_name, v) + ('' if category == 'install' else '-src')
                                test = 'test' if 'test' in p.version_hints[v] else 'stable'
                                ts = time.strftime('%Y-%m-%d %H:%M', time.gmtime(p.tar(v, category).mtime))
                                print('<tr><td>%s</td><td class="right">%d KiB</td><td>%s</td><td>[<a href="../%s/%s/%s">list of files</a>]</td><td>%s</td></tr>' % (name, size, ts, arch, pn, target, test), file=f)

                            for version in sorted(packages[arch][p].versions(), key=lambda v: SetupVersion(v)):
                                tar_line(p, packages[arch][p], 'install', version, arch, f)
                                tar_line(p, packages[arch][p], 'source', version, arch, f)

                            print('</table><br>', file=f)
                    print('</ul>', file=f)

                    if po.kind == package.Kind.source:
                        repo = 'git/cygwin-packages/%s.git' % pn
                        if os.path.exists('/' + repo):
                            repo_browse_url = '/git-cygwin-packages/?p=%s' % repo
                            print('<span class="detail">packaging repository</span>: <a href="%s">%s.git</a>' % (repo_browse_url, pn), file=f)

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


#
# write package index page fragment for inclusion
#
def write_packages_inc(args, packages, name, kind, includer):
    packages_inc = os.path.join(args.htdocs, name)
    if not args.dryrun:

        def touch_including(changed):
            if changed:
                # touch the including file for the benefit of 'XBitHack full'
                package_list = os.path.join(args.htdocs, includer)
                if os.path.exists(package_list):
                    logging.info("touching %s for the benefit of 'XBitHack full'" % (package_list))
                    utils.touch(package_list)

        with utils.open_amifc(packages_inc, cb=touch_including) as index:
            os.fchmod(index.fileno(), 0o644)

            # This list contains all packages in any arch. Source packages
            # appear under their original package name.
            package_list = {}
            for arch in packages:
                for p in packages[arch]:
                    if p.endswith('-debuginfo'):
                        continue

                    if packages[arch][p].kind == package.Kind.binary:
                        if packages[arch][p].skip:
                            continue

                    if packages[arch][p].kind == kind:
                        package_list[packages[arch][p].orig_name] = p

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

                po = arch_package(packages, p)
                if not po:
                    continue

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


def write_arch_listing(args, packages, arch):
    update_summary = set()
    base = os.path.join(args.htdocs, arch)
    ensure_dir_exists(args, base)

    #
    # write base directory .htaccess, if needed
    #
    # force trying to access the base directory to redirect to the package list
    # page, as having the server index this directory containing lots of
    # subdirectories makes this URL very expensive to serve if someone stumbles
    # onto it by accident)
    #

    htaccess = os.path.join(base, '.htaccess')
    if not os.path.exists(htaccess) or args.force:
        if not args.dryrun:
            with utils.open_amifc(htaccess) as f:

                print('Redirect temp /packages/%s/index.html https://cygwin.com/packages/package_list.html' % (arch),
                      file=f)

    toremove = glob.glob(os.path.join(base, '*', '*')) + glob.glob(os.path.join(base, '*', '.*'))

    for p in packages:

        dirpath = os.path.join(base, p)
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
        if os.path.exists(dirpath):
            listings = os.listdir(dirpath)
            listings.remove('.htaccess')
        else:
            listings = []

        for tn, to in itertools.chain.from_iterable([packages[p].tars[vr].items() for vr in packages[p].tars]):
            fver = re.sub(r'\.tar.*$', '', tn)
            listing = os.path.join(dirpath, fver)

            # ... if it doesn't already exist, or --force --force
            if not os.path.exists(listing) or (args.force > 1):

                if not args.dryrun:
                    # versions are being added, so summary needs updating
                    update_summary.add(p)

                    with utils.open_amifc(listing) as f:
                        bv = packages[p].best_version
                        header = p + ": " + sdesc(packages[p], bv)

                        if fver.endswith('-src'):
                            header = header + " (source)"

                        print(textwrap.dedent('''\
                                                 <!DOCTYPE html>
                                                 <html>
                                                 <head>
                                                 <title>%s</title>
                                                 </head>
                                                 <body>
                                                 <h1>%s</h1>
                                                 <pre>''' % (header, header)), file=f)

                        tf = os.path.join(args.rel_area, to.path, to.fn)
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
                            except Exception as e:
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

            if fver in listings:
                listings.remove(fver)

        # some versions remain on toremove list, and will be removed, so summary
        # needs updating
        if listings:
            update_summary.add(p)

    #
    # remove any remaining files for which there was no corresponding package
    #

    for r in toremove:
        logging.debug('rm %s' % r)
        if not args.dryrun:
            os.unlink(r)

            #
            # remove any directories which are now empty
            #

            dirpath = os.path.dirname(r)
            if len(os.listdir(dirpath)) == 0:
                logging.debug('rmdir %s' % dirpath)
                os.rmdir(os.path.join(dirpath))

    return update_summary


if __name__ == "__main__":
    htdocs_default = os.path.join(common_constants.HTDOCS, 'packages')
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='Write HTML package listings')
    parser.add_argument('--arch', action='store', required=True, choices=common_constants.ARCHES)
    parser.add_argument('--force', action='store_true', help="overwrite existing files")
    parser.add_argument('--htdocs', action='store', metavar='DIR', help="htdocs output directory (default: " + htdocs_default + ")", default=htdocs_default)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    parser.add_argument('-n', '--dry-run', action='store_true', dest='dryrun', help="don't do anything")
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output')
    (args) = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    packages = package.read_packages(args.rel_area, args.arch)
    update_package_listings(args, packages, args.arch)

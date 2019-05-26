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
import os
import re
import sys
import tarfile
import textwrap
import time

from .version import SetupVersion
from . import common_constants
from . import maintainers
from . import package


#
# get sdesc for a package
#
# some source-only packages don't have an sdesc, since they consist of just
# 'skip':', in which case we try to make a reasonable one
#

def sdesc(packages, p, bv):
    if 'sdesc' in packages[p].version_hints[bv]:
        header = packages[p].version_hints[bv]['sdesc']
    else:
        header = p

    return header.replace('"', '')


# ditto for ldesc

def ldesc(packages, p, bv):
    if 'ldesc' in packages[p].version_hints[bv]:
        header = packages[p].version_hints[bv]['ldesc']
    else:
        header = p

    return header.replace('"', '')


# ensure a directory exists
#
# for some versions of python, os.makedirs() can still raise FileExistsError
# even when exists_ok=True, if the directory mode is not as expected.

def ensure_dir_exists(args, path):
    if not args.dryrun:
        try:
            os.makedirs(path, exist_ok=True)
        except FileExistsError:
            pass
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

    mlist = maintainers.Maintainer.read(args, None)
    pkg_maintainers = maintainers.Maintainer.invert(mlist)

    toremove = glob.glob(os.path.join(summaries, '*'))

    def linkify_package(p):
        if p in package_list:
            return '<a href="%s.html">%s</a>' % (p, p)
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
            logging.debug('writing %s' % summary)
            if not args.dryrun:
                with open(summary, 'w') as f:
                    os.fchmod(f.fileno(), 0o755)

                    arch_packages = None
                    for arch in common_constants.ARCHES:
                        if p in packages[arch]:
                            arch_packages = packages[arch]
                            break

                    if not arch_packages:
                        continue

                    bv = arch_packages[p].best_version
                    title = "Cygwin Package Summary for %s" % p

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
                    <h1>Package: %s</h1>''' % (title, p)), file=f)

                    print('<span class="detail">sdesc</span>: %s<br><br>' % sdesc(arch_packages, p, bv), file=f)
                    print('<span class="detail">ldesc</span>: %s<br><br>' % ldesc(arch_packages, p, bv), file=f)
                    print('<span class="detail">categories</span>: %s<br><br>' % arch_packages[p].version_hints[bv].get('category', ''), file=f)

                    for key in ['depends', 'obsoletes', 'provides', 'conflicts', 'build-depends']:
                        value = arch_packages[p].version_hints[bv].get(key, None)
                        if value:
                            print('<span class="detail">%s</span>: %s<br><br>' % (key, ', '.join([linkify_package(p) for p in value.split(', ')])), file=f)

                    es = arch_packages[p].version_hints[bv].get('external-source', None)
                    if es:
                        print('<span class="detail">source</span>: %s<br><br>' % linkify_package(es), file=f)
                    else:
                        print('<span class="detail">binaries</span>: %s<br><br>' % ', '.join([linkify_package(p) for p in sorted(arch_packages[p].is_used_by)]), file=f)
                        es = p

                    if 'ORPHANED' in pkg_maintainers[es]:
                        m = 'ORPHANED'
                    else:
                        m = ', '.join(sorted(pkg_maintainers[es]))
                    print('<span class="detail">maintainer(s)</span>: %s ' % m, file=f)
                    print(textwrap.dedent('''\
                    <span class="smaller">(Use <a href="https://cygwin.com/lists.html#cygwin">the mailing list</a> to report bugs or ask questions.
                    <a href="https://cygwin.com/problems.html#personal-email">Do not contact the maintainer(s) directly</a>.)</span>'''), file=f)
                    print('<br><br>', file=f)

                    print('<ul>', file=f)
                    for arch in sorted(packages):
                        if p in packages[arch]:

                            print('<li><span class="detail">%s</span></li>' % arch, file=f)

                            print('<table class="pkgtable">', file=f)
                            print('<tr><th>Version</th><th>Package Size</th><th>Files</th><th>Status</th></tr>', file=f)

                            def tar_line(pn, p, category, v, arch, f):
                                if category not in p.vermap[v]:
                                    return
                                t = p.vermap[v][category]
                                size = round(p.tar(v, category).size / 1024)
                                name = v if category == 'install' else v + ' (source)'
                                target = "%s-%s" % (pn, v) + ('' if category == 'install' else '-src')
                                test = 'test' if 'test' in p.version_hints[v] else 'stable'
                                print('<tr><td>%s</td><td class="right">%d kB</td><td>[<a href="../%s/%s/%s">list of files</a>]</td><td>%s</td></tr>' % (name, size, arch, pn, target, test), file=f)

                            for version in sorted(packages[arch][p].vermap.keys(), key=lambda v: SetupVersion(v)):
                                tar_line(p, packages[arch][p], 'install', version, arch, f)
                                tar_line(p, packages[arch][p], 'source', version, arch, f)

                            print('</table><br>', file=f)
                    print('</ul>', file=f)

                    print(textwrap.dedent('''\
                    </div>
                    </body>
                    </html>'''), file=f)

    for r in toremove:
        logging.debug('rm %s' % r)
        if not args.dryrun:
            os.unlink(r)

    #
    # write packages.inc
    #

    packages_inc = os.path.join(args.htdocs, 'packages.inc')
    logging.debug('writing %s' % packages_inc)
    if not args.dryrun:
        with open(packages_inc, 'w') as index:
            os.fchmod(index.fileno(), 0o755)
            print(textwrap.dedent('''\
                                     <table class="pkglist">'''), file=index)

            for p in sorted(package_list, key=package.sort_key):
                if p.endswith('-debuginfo'):
                    continue

                arch_packages = None
                for arch in common_constants.ARCHES:
                    if p in packages[arch]:
                        arch_packages = packages[arch]
                        break

                if not arch_packages:
                    continue

                bv = arch_packages[p].best_version
                header = sdesc(arch_packages, p, bv)

                print('<tr><td><a href="summary' + '/' + p + '.html">' + p + '</a></td><td>' + html.escape(header, quote=False) + '</td></tr>', file=index)

            print(textwrap.dedent('''\
                                     </table>
                                     '''), file=index)


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
        logging.debug('writing %s' % htaccess)
        if not args.dryrun:
            with open(htaccess, 'w') as f:

                print('Redirect temp /packages/%s/index.html https://cygwin.com/packages/package_list.html' % (arch),
                      file=f)

    toremove = glob.glob(os.path.join(base, '*', '*')) + glob.glob(os.path.join(base, '*', '.*'))

    for p in packages:

        dir = os.path.join(base, p)
        ensure_dir_exists(args, dir)

        #
        # write .htaccess if needed
        #

        htaccess = os.path.join(dir, '.htaccess')
        if not os.path.exists(htaccess):
            logging.debug('writing %s' % htaccess)
            if not args.dryrun or args.force:
                with open(htaccess, 'w') as f:
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
        listings = os.listdir(dir)
        listings.remove('.htaccess')

        for t in itertools.chain.from_iterable([packages[p].tars[vr] for vr in packages[p].tars]):
            fver = re.sub(r'\.tar.*$', '', t)
            listing = os.path.join(dir, fver)

            # ... if it doesn't already exist, or force
            if not os.path.exists(listing) or args.force:

                logging.debug('writing %s' % listing)

                if not args.dryrun:
                    # versions are being added, so summary needs updating
                    update_summary.add(p)

                    with open(listing, 'w') as f:
                        bv = packages[p].best_version
                        header = p + ": " + sdesc(packages, p, bv)

                        if fver.endswith('-src'):
                            header = header + " (source code)"

                        header = html.escape(header, quote=False)

                        print(textwrap.dedent('''\
                                                 <!DOCTYPE html>
                                                 <html>
                                                 <head>
                                                 <title>%s</title>
                                                 </head>
                                                 <body>
                                                 <h1>%s</h1>
                                                 <pre>''' % (header, header)), file=f)

                        tf = os.path.join(args.rel_area, packages[p].path, t)
                        if not os.path.exists(tf):
                            # this shouldn't happen with a full mirror
                            logging.error("tarfile %s not found" % (tf))
                        elif os.path.getsize(tf) <= 32:
                            # compressed empty files aren't a valid tar file,
                            # but we can just ignore them
                            pass
                        else:
                            try:
                                with tarfile.open(tf) as a:
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

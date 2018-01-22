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

from . import common_constants
from . import package


#
# get sdesc for a package
#
# some source-only packages don't have an sdesc, since they consist of just
# 'skip':', in which case we try to make a reasonable one
#

def desc(packages, p, bv):
    if 'sdesc' in packages[p].version_hints[bv]:
        header = packages[p].version_hints[bv]['sdesc']
    else:
        header = p

    return header.replace('"', '')


#
#
#

def update_package_listings(args, packages, arch):
    base = os.path.join(args.htdocs, arch)
    if not args.dryrun:
        try:
            os.makedirs(base, exist_ok=True)
        except FileExistsError:
            pass

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
        if not args.dryrun:
            try:
                os.makedirs(dir, exist_ok=True)
            except FileExistsError:
                pass
            os.chmod(dir, 0o777)

        #
        # write .htaccess if needed
        #

        htaccess = os.path.join(dir, '.htaccess')
        if not os.path.exists(htaccess):
            logging.debug('writing %s' % htaccess)
            if not args.dryrun or args.force:
                with open(htaccess, 'w') as f:

                    print(textwrap.dedent('''\
                                             Options Indexes
                                             IndexOptions -FancyIndexing
                                             AddType text/html 1 2 3 4 5 6 7 8 9'''),
                          file=f)
                    # XXX: omitting 0 here doesn't make much sense.  and this
                    # doesn't help for src packages, so is it actually having
                    # any effect?

        # this file should exist, so remove from the toremove list
        if htaccess in toremove:
            toremove.remove(htaccess)

        #
        # for each tarfile, write tarfile listing
        #

        for t in itertools.chain.from_iterable([packages[p].tars[vr] for vr in packages[p].tars]):
            fver = re.sub(r'\.tar.*$', '', t)
            listing = os.path.join(dir, fver)

            # ... if it doesn't already exist, or force
            if not os.path.exists(listing) or args.force:

                logging.debug('writing %s' % listing)

                if not args.dryrun:
                    with open(listing, 'w') as f:
                        bv = packages[p].best_version
                        header = p + ": " + desc(packages, p, bv)

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

    #
    # write packages.inc
    #

    packages_inc = os.path.join(base, 'packages.inc')
    logging.debug('writing %s' % packages_inc)
    if not args.dryrun:
        with open(packages_inc, 'w') as index:
            os.fchmod(index.fileno(), 0o755)
            print(textwrap.dedent('''\
                                     <div id="%s">
                                     <div class="background">
                                     <b class="rtop"><b class="r1"></b><b class="r2"></b><b class="r3"></b><b class="r4"></b></b>
                                     <h2>Available Packages for %s</h2>
                                     <b class="rbottom"><b class="r4"></b><b class="r3"></b><b class="r2"></b><b class="r1"></b></b>
                                     </div>
                                     <table class="pkglist">''') % (arch, arch), file=index)

            for p in sorted(packages.keys(), key=package.sort_key):

                bv = packages[p].best_version
                header = desc(packages, p, bv)

                print('<tr><td><a href="' + arch + '/' + p + '">' + p + '</a></td><td>' + html.escape(header, quote=False) + '</td></tr>', file=index)

            print(textwrap.dedent('''\
                                     </table>
                                     </div>'''), file=index)

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

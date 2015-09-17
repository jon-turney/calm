#!/usr/bin/env python3
#
# write package listing HTML files
#
# - build a list of all files under HTDOCS/packages/<arch>
# - for each tar file listed in setup.ini
# -- if a package listing HTML file doesn't already exist
# --- write a HTML package listing file listing the tar file contents
# -- also create a .htaccess file if not present
# - write packages.inc, the list of packages
# - remove any listing files for which there was no package
# - remove any empty directories
#

import os
import glob
import tarfile
import time
import re
import textwrap
import logging
import argparse
import sys
from collections import defaultdict

import common_constants
import package

#
#
#

def main(args):

    packages = package.read_packages(args.rel_area, args.arch)

    base = os.path.join(args.htdocs, args.arch)
    os.makedirs(base, exist_ok=True)

    toremove = glob.glob(os.path.join(base, '*', '*'))

    for p in packages.keys():

        dir = os.path.join(base, p)
        os.makedirs(dir, exist_ok=True)
        os.chmod(dir, 0o777)

        #
        # write .htaccess if needed
        #

        htaccess = os.path.join(dir, '.htaccess')
        if not os.path.exists(htaccess):
            logging.info('Writing %s' % htaccess)
            if not args.dryrun:
                with open(htaccess, 'w') as f:

                    print(textwrap.dedent('''\
                                             Options Indexes
                                             IndexOptions -FancyIndexing
                                             AddType text/html 1 2 3 4 5 6 7 8 9'''),
                                          file=f)
                    # XXX: omitting 0 here doesn't make much sense
                    # this doesn't help for src packages, so is it actually having any effect?

        #
        # for each tarfile, write tarfile listing, if needed
        #

        for t in packages[p].tars:

            fver = os.path.basename(t)
            fver = re.sub(r'\.tar.*$', '', fver)
            html = os.path.join(dir, fver)

            if not os.path.exists(html):
                if 'skip' in packages[p].hints:
                    continue

                logging.info('Writing %s' % html)

                if not args.dryrun:
                    with open(html, 'w') as f:
                        header = p + ": " + packages[p].hints['sdesc'].replace('"', '')
                        if fver.endswith('-src'):
                            header = header + " (source code)"
                        else:
                            header = header + " (installed binaries and support files)"
                        # XXX: also recognize '-debuginfo' ?

                        print(textwrap.dedent('''\
                                                 <html>
                                                 <h1>%s</h1>
                                                 <tt><pre>''' % (header)), file=f)

                        tf = os.path.join(common_constants.FTP, t)
                        if os.path.exists(tf):

                            # compressed empty files aren't a valid tar file, but we can
                            # just ignore them
                            if (os.path.getsize(tf) <= 32):
                                continue

                            a = tarfile.open(tf)
                            for i in a:
                                print('    %-16s%12d %s' % (time.strftime('%Y-%m-%d %H:%M', time.gmtime(i.mtime)), i.size, i.name), file=f, end='')
                                if i.isdir():
                                    print('/', file=f, end='')
                                if i.issym() or i.islnk():
                                    print(' -> %s' % i.linkname, file=f, end='')
                                print('', file=f)
                        else:
                            # XXX: this shouldn't happen with a full mirror...
                            print('tarfile %s not found' % tf, file=f)

                        print(textwrap.dedent('''\
                                                 </pre></tt>
                                                 </html>'''), file=f)
            else:
                logging.info('Not writing %s, already exists' % html)

            # this file should exist, so remove from the toremove list
            if html in toremove:
                toremove.remove(html)

    #
    # write packages.inc
    #

    packages_inc = os.path.join(base, 'packages.inc')
    logging.info('Writing %s' % packages_inc)
    if not args.dryrun:
        with open(packages_inc, 'w') as index:
            os.fchmod(index.fileno(), 0o755)
            print(textwrap.dedent('''\
                                     <div id="%s">
                                     <div id="background">
                                     <b class="rtop"><b class="r1"></b><b class="r2"></b><b class="r3"></b><b class="r4"></b></b>
                                     <h2>Available Packages for %s</h2>
                                     <b class="rbottom"><b class="r4"></b><b class="r3"></b><b class="r2"></b><b class="r1"></b></b>
                                     </div>
                                     <br>
                                     <table class="pkglist">''') % (args.arch, args.arch), file=index)

            for p in sorted(packages.keys(), key=package.sort_key):
                # don't write anything if 'skip'
                if 'skip' in packages[p].hints:
                    continue

                header = packages[p].hints['sdesc'].replace('"', '')

                print('<tr><td><a href="' + args.arch + '/' +  p + '">' + p + '</a></td><td>' + header  + '</td></tr>', file=index)

            print(textwrap.dedent('''\
                                     </table>
                                     </div>'''), file=index)

    #
    # remove any remaining listing files for which there was no corresponding package
    #

    for r in toremove:
        logging.info('rm %s' % r)
        if not args.dryrun:
            os.unlink(r)

if __name__ == "__main__":
    htdocs_default = os.path.join(common_constants.HTDOCS, 'packages')
    relarea_default = common_constants.FTP

    parser = argparse.ArgumentParser(description='Write HTML package listings')
    parser.add_argument('-v', '--verbose', action='count', dest = 'verbose', help='verbose output')
    parser.add_argument('-n', '--dry-run', action='store_true', dest = 'dryrun', help="don't do anything")
    parser.add_argument('--arch', action='store', required=True, choices=common_constants.ARCHES)
    parser.add_argument('--htdocs', action='store', metavar='DIR', help="htdocs output directory (default: " + htdocs_default + ")", default=htdocs_default)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    # XXX: should support a 'force' action to write files even though they already exist
    (args) = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    logging.basicConfig(format=os.path.basename(sys.argv[0])+': %(message)s')

    main(args)

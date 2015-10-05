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
# upload directory processing
#

from collections import defaultdict
import filecmp
import os
import logging

import package


#
#
#

def scan(m, all_packages, args):
    basedir = os.path.join(m.homedir(), args.arch)
    releasedir = os.path.join(args.rel_area, args.arch)

    packages = defaultdict(package.Package)
    move = defaultdict(list)
    readys = []
    sums = []
    error = False
    mtime = 0

    logging.info('reading packages from %s' % (basedir))

    # note mtime of !ready file
    for ready in [os.path.join(basedir, '!ready'), os.path.join(basedir, 'release', '!ready')]:
        if os.path.exists(ready):
            mtime = os.path.getmtime(ready)
            logging.info('processing files with mtime older than %d' % (mtime))
            readys.append(ready)

    # scan package directories
    for (dirpath, subdirs, files) in os.walk(os.path.join(basedir, 'release')):
        relpath = os.path.relpath(dirpath, basedir)

        # skip uninteresting directories
        if (not files) or (relpath == 'release'):
            continue

        logging.info('reading uploads from %s' % dirpath)

        # It really only makes sense for !ready to be in the basedir, or
        # basedir/release, but historically we have accepted it anywhere, which
        # affected all files thereafter in some unspecified directory traversal.
        if '!ready' in files:
            logging.error("!ready at %s not supported, ignored" % relpath)
            files.remove('!ready')

        # package doesn't appear in package list at all
        pkgname = os.path.basename(dirpath)
        if pkgname not in all_packages:
            logging.error("%s is not in the package list" % pkgname)
            continue

        # only process packages for which we are listed as a maintainer
        if pkgname not in m.pkgs:
            logging.warn("%s is not in the package list for maintainer %s" % (pkgname, m.name))
            continue

        # ensure sha512.sum exists
        # XXX: either we make read_package able to calculate sh512 sum when
        # sha512.sum doesn't exist, or we make sure shs512.sum exists.  Not
        # sure which is the better approach.
        if 'sha512.sum' not in files:
            logging.info('generating sha512.sum')
            os.system("cd '%s' ; sha512sum * >sha512.sum" % os.path.join(dirpath))
            files.append('sha512.sum')

        # filter out files we don't need to consider
        for f in sorted(files):
            fn = os.path.join(dirpath, f)
            rel_fn = os.path.join(relpath, f)
            logging.info("processing %s" % rel_fn)

            # ignore !packages (which we no longer use)
            # ignore !mail and !email (which we have already read)
            if f in ['!packages', '!mail', '!email']:
                files.remove(f)
                continue

            if f == 'sha512.sum':
                sums.append(fn)
                continue

            # only process files newer than !ready
            if os.path.getmtime(fn) > mtime:
                if mtime == 0:
                    logging.warn("ignoring %s as there is no !ready" % rel_fn)
                else:
                    logging.warn("ignoring %s as it is newer than !ready" % rel_fn)
                files.remove(f)
                continue

            if f.startswith('-'):
                logging.error("file deletion request %s not implemented yet" % rel_fn)
                files.remove(f)
            else:
                dest = os.path.join(releasedir, relpath, f)
                if os.path.isfile(dest):
                    if filecmp.cmp(dest, fn, shallow=False):
                        logging.warn("identical %s already in release area, ignoring" % rel_fn)
                    else:
                        logging.error("different %s already in release area" % rel_fn)
                        error = True
                else:
                    move[relpath].append(f)

        # read and validate package
        if files:
            # strict means we consider warnings as fatal for upload
            if package.read_package(packages, basedir, dirpath, files, strict=True):
                error = True

    return (error, packages, move, readys, sums)


#
#
#

def remove(args, readys):
    for f in readys:
        logging.info("rm %s", f)
        if not args.dryrun:
            os.unlink(f)


#
#
#

def move(m, args, move):
    basedir = os.path.join(m.homedir(), args.arch)
    releasedir = os.path.join(args.rel_area, args.arch)

    for p in move:
        logging.info("mkdir %s" % os.path.join(releasedir, p))
        if not args.dryrun:
            os.makedirs(os.path.join(releasedir, p), exist_ok=True)
        for f in move[p]:
            logging.info("move %s to %s" % (os.path.join(basedir, p, f), os.path.join(releasedir, p, f)))
            if not args.dryrun:
                os.rename(os.path.join(basedir, p, f), os.path.join(releasedir, p, f))

        # Update sha512.sum file in target directory
        #
        # (this means that upset can use that file unconditionally, rather than
        # having to have a special case to generate the hash itself for when
        # that file hasn't yet been created by sourceware.org scripts)
        if not args.dryrun:
            os.system("cd '%s' ; sha512sum * >sha512.sum" % os.path.join(releasedir, p))

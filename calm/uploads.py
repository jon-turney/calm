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

from collections import defaultdict, namedtuple
import filecmp
import os
import logging
import re
import shutil
import tarfile
import time

from . import package

# reminders will be issued daily
REMINDER_INTERVAL = 60*60*24

# a named tuple type to hold the result of scan
ScanResult = namedtuple('ScanResult', 'error,packages,to_relarea,to_vault,remove_always,remove_success')


#
#
#

def scan(m, all_packages, arch, args):
    basedir = os.path.join(m.homedir(), arch)

    packages = defaultdict(package.Package)
    move = defaultdict(list)
    vault = defaultdict(list)
    remove = []
    remove_success = []
    error = False
    mtimes = [('', 0)]

    logging.debug('reading packages from %s' % (basedir))

    # note mtime of any !ready file at top-level
    for ready in [os.path.join(basedir, '!ready'), os.path.join(basedir, 'release', '!ready')]:
        if os.path.exists(ready):
            mtime = os.path.getmtime(ready)
            mtimes.append(('', mtime))
            logging.debug('processing files with mtime older than %d' % (mtime))
            remove.append(ready)

    # we record a timestamp when 'ignoring as there is no !ready' warnings were
    # last emitted
    logging.debug("reminder-timestamp %d, interval %d, next reminder %d, current time %d" % (m.reminder_time, REMINDER_INTERVAL, m.reminder_time + REMINDER_INTERVAL, time.time()))

    # scan package directories
    for (dirpath, subdirs, files) in os.walk(os.path.join(basedir, 'release')):
        relpath = os.path.relpath(dirpath, m.homedir())
        removed_files = []

        # skip uninteresting directories
        if (not files) or (relpath == os.path.join(arch, 'release')):
            continue

        logging.debug('reading uploads from %s' % dirpath)

        # note the mtime of the !ready file
        if '!ready' in files:
            ready = os.path.join(dirpath, '!ready')
            mtime = os.path.getmtime(ready)
            mtimes.append((relpath + '/', mtime))
            remove.append(ready)
            files.remove('!ready')
            logging.debug("processing files below '%s' with mtime older than %d" % (relpath, mtime))
        else:
            # otherwise work back up a list of (path,mtimes) (which should be in
            # shortest-to-longest order, since os.walk() walks the tree
            # top-down), and use the mtime of the first (longest) matching path.
            while True:
                (path, mtime) = mtimes[-1]
                if relpath.startswith(path):
                    logging.debug("using mtime %d from subpath '%s' of '%s'" % (mtime, path, relpath))
                    break
                else:
                    mtimes.pop()

        # package doesn't appear in package list at all
        if not package.is_in_package_list(relpath, all_packages):
            logging.error("package '%s' is not in the package list" % dirpath)
            continue

        # only process packages for which we are listed as a maintainer
        if not package.is_in_package_list(relpath, m.pkgs):
            logging.warning("package '%s' is not in the package list for maintainer %s" % (dirpath, m.name))
            continue

        # filter out files we don't need to consider
        for f in sorted(files):
            fn = os.path.join(dirpath, f)
            rel_fn = os.path.join(relpath, f)
            logging.debug("processing %s" % rel_fn)

            # ignore !packages (which we no longer use)
            # ignore !mail and !email (which we have already read)
            if f in ['!packages', '!mail', '!email']:
                files.remove(f)
                continue

            # ignore in-progress sftp uploads. Net::SFTP::SftpServer uses
            # temporary upload filenames ending with '.SftpXFR.<pid>'
            if re.search(r'\.SftpXFR\.\d*$', f):
                logging.debug("ignoring temporary upload file %s" % fn)
                files.remove(f)
                continue

            # only process files newer than !ready
            if os.path.getmtime(fn) > mtime:
                if mtime == 0:
                    m.reminders_timestamp_checked = True
                    lvl = logging.DEBUG

                    # if more than REMINDER_INTERVAL has elapsed since we warned
                    # about files being ignored, warn again
                    if time.time() > (m.reminder_time + REMINDER_INTERVAL):
                        lvl = logging.WARNING
                        if not args.dryrun:
                            m.reminders_issued = True

                    logging.log(lvl, "ignoring %s as there is no !ready" % fn)
                else:
                    logging.warning("ignoring %s as it is newer than !ready" % fn)
                files.remove(f)
                continue

            # a remove file, which indicates some other file should be removed
            if f.startswith('-'):
                if ('*' in f) or ('?' in f):
                    logging.error("remove file %s name contains metacharacters, which are no longer supported" % fn)
                    error = True
                elif os.path.getsize(fn) != 0:
                    logging.error("remove file %s is not empty" % fn)
                    error = True
                elif f == '-setup.hint':
                    logging.error("remove file %s is not permitted" % fn)
                    error = True
                else:
                    vault[relpath].append(f[1:])
                    remove_success.append(fn)
                    removed_files.append(f[1:])
                files.remove(f)
                continue

            # warn about legacy setup.hint uploads
            if f == 'setup.hint':
                logging.warning("'%s' seen, please update to cygport >= 0.23.0" % fn)

            # verify compressed archive files are valid
            if re.search(r'\.tar\.(bz2|gz|lzma|xz)$', f):
                valid = True

                # accept a compressed empty file, even though it isn't a valid
                # compressed archive
                if os.path.getsize(fn) > 32:
                    try:
                        # we need to extract all of an archive contents to validate
                        # it
                        with tarfile.open(fn) as a:
                            a.getmembers()
                    except Exception as e:
                        valid = False
                        logging.error("exception %s while reading %s" % (type(e).__name__, fn))
                        logging.debug('', exc_info=True)

                if not valid:
                    files.remove(f)
                    continue

            # does file already exist in release area?
            dest = os.path.join(args.rel_area, relpath, f)
            if os.path.isfile(dest):
                if not f.endswith('.hint'):
                    if filecmp.cmp(dest, fn, shallow=False):
                        logging.info("ignoring, identical %s is already in release area" % fn)
                    else:
                        logging.error("ignoring, different %s is already in release area (perhaps you should rebuild with a different version-release identifier?)" % fn)
                        error = True
                    files.remove(f)
                else:
                    if filecmp.cmp(dest, fn, shallow=False):
                        logging.debug("identical %s is already in release area" % fn)
                    else:
                        logging.debug("different %s is already in release area" % fn)
                    # we always consider .hint files as needing to be moved, as
                    # we currently can't have a valid package without one
                    move[relpath].append(f)
            else:
                move[relpath].append(f)

        # read and validate package
        if files:
            # strict means we consider warnings as fatal for upload
            if package.read_package(packages, m.homedir(), dirpath, files, strict=True, remove=removed_files, upload=True):
                error = True

    # always consider timestamp as checked during a dry-run, so it is never
    # reset
    if args.dryrun:
        m.reminders_timestamp_checked = True

    return ScanResult(error, packages, move, vault, remove, remove_success)


#
#
#

def remove(args, remove):
    for f in remove:
        logging.debug("rm %s", f)
        if not args.dryrun:
            os.unlink(f)


#
#
#

def move(args, movelist, fromdir, todir):
    for p in sorted(movelist):
        logging.debug("mkdir %s" % os.path.join(todir, p))
        if not args.dryrun:
            try:
                os.makedirs(os.path.join(todir, p), exist_ok=True)
            except FileExistsError:
                pass
        logging.debug("move from '%s' to '%s':" % (os.path.join(fromdir, p), os.path.join(todir, p)))
        for f in sorted(movelist[p]):
            if os.path.exists(os.path.join(fromdir, p, f)):
                logging.info("%s" % os.path.join(p, f))
                if not args.dryrun:
                    os.rename(os.path.join(fromdir, p, f), os.path.join(todir, p, f))
            else:
                logging.error("%s can't be moved as it doesn't exist" % (f))


def move_to_relarea(m, args, movelist):
    if movelist:
        logging.info("move from %s's upload area to release area:" % (m.name))
    move(args, movelist, m.homedir(), args.rel_area)
    # XXX: Note that there seems to be a separate process, not run from
    # cygwin-admin's crontab, which changes the ownership of files in the
    # release area to cyguser:cygwin


def move_to_vault(args, movelist):
    if movelist:
        logging.info("move from release area to vault:")
    move(args, movelist, args.rel_area, args.vault)


# compute the intersection of a pair of movelists
def movelist_intersect(a, b):
    i = defaultdict(list)
    for p in a.keys() & b.keys():
        pi = set(a[p]) & set(b[p])
        if pi:
            i[p] = pi
    return i


#
#
#

def copy(args, movelist, fromdir, todir):
    for p in sorted(movelist):
        logging.debug("mkdir %s" % os.path.join(todir, p))
        if not args.dryrun:
            try:
                os.makedirs(os.path.join(todir, p), exist_ok=True)
            except FileExistsError:
                pass
        logging.debug("copy from '%s' to '%s':" % (os.path.join(fromdir, p), os.path.join(todir, p)))
        for f in sorted(movelist[p]):
            if os.path.exists(os.path.join(fromdir, p, f)):
                logging.debug("%s" % (f))
                if not args.dryrun:
                    shutil.copy2(os.path.join(fromdir, p, f), os.path.join(todir, p, f))
            else:
                logging.error("%s can't be copied as it doesn't exist" % (f))

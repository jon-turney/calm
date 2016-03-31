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
import re
import time

import package

# reminders will be issued daily
REMINDER_INTERVAL = 60*60*24


#
#
#

def scan(m, all_packages, args):
    basedir = os.path.join(m.homedir(), args.arch)
    releasedir = os.path.join(args.rel_area, args.arch)

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

    # the mtime of this file indicates when 'ignoring as there is no !ready'
    # warnings were last emitted
    reminder_file = os.path.join(basedir, '!reminder-timestamp')
    if os.path.exists(reminder_file):
        reminder_time = os.path.getmtime(reminder_file)
    else:
        reminder_time = 0
    reminders = False
    logging.debug("reminder-timestamp %d, interval %d, next reminder %d, current time %d" % (reminder_time, REMINDER_INTERVAL, reminder_time + REMINDER_INTERVAL, time.time()))

    # scan package directories
    for (dirpath, subdirs, files) in os.walk(os.path.join(basedir, 'release')):
        relpath = os.path.relpath(dirpath, basedir)

        # skip uninteresting directories
        if (not files) or (relpath == 'release'):
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

            # only process files newer than !ready
            if os.path.getmtime(fn) > mtime:
                if mtime == 0:
                    reminders = True
                    lvl = logging.INFO

                    # if more than REMINDER_INTERVAL has elapsed since we warned
                    # about files being ignored, warn again
                    if time.time() > (reminder_time + REMINDER_INTERVAL):
                        lvl = logging.WARNING
                        if not args.dryrun:
                            touch(reminder_file)

                    logging.log(lvl, "ignoring %s as there is no !ready" % fn)
                else:
                    logging.warning("ignoring %s as it is newer than !ready" % fn)
                files.remove(f)
                continue

            if f.startswith('-'):
                vault[relpath].append(f[1:])
                files.remove(f)
                remove_success.append(fn)
            else:
                dest = os.path.join(releasedir, relpath, f)
                if os.path.isfile(dest):
                    if f != 'setup.hint':
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
                            logging.warning("replacing, different %s is already in release area" % fn)
                        # we always consider setup.hint, as we can't have a valid package without it
                        move[relpath].append(f)
                else:
                    move[relpath].append(f)

        # read and validate package
        if files:
            # strict means we consider warnings as fatal for upload
            if package.read_package(packages, basedir, dirpath, files, strict=True):
                error = True

    # if we didn't need to check the reminder timestamp, it can be reset
    if not reminders and not args.dryrun:
        try:
            os.remove(reminder_file)
        except FileNotFoundError:
            pass

    return (error, packages, move, vault, remove, remove_success)


#
#
#

def touch(fn, times=None):
    with open(fn, 'a'):
        os.utime(fn, times)


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
        logging.info("move from '%s' to '%s':" % (os.path.join(fromdir, p), os.path.join(todir, p)))
        for f in sorted(movelist[p]):
            if os.path.exists(os.path.join(fromdir, p, f)):
                logging.info("%s" % (f))
                if not args.dryrun:
                    os.rename(os.path.join(fromdir, p, f), os.path.join(todir, p, f))
            else:
                logging.error("%s can't be moved as it doesn't exist" % (f))


def move_to_relarea(m, args, movelist):
    move(args, movelist, os.path.join(m.homedir(), args.arch), os.path.join(args.rel_area, args.arch))
    # XXX: Note that there seems to be a separate process, not run from
    # cygwin-admin's crontab, which changes the ownership of files in the
    # release area to cyguser:cygwin


def move_to_vault(args, movelist):
    move(args, movelist, os.path.join(args.rel_area, args.arch), os.path.join(args.vault, args.arch))

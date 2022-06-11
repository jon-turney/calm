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
import time
import xtarfile

from .movelist import MoveList
from . import common_constants
from . import fixes
from . import package

# reminders will be issued weekly
REMINDER_INTERVAL = 60 * 60 * 24 * 7
# reminders don't start to be issued until an hour after upload
REMINDER_GRACE = 60 * 60

# a named tuple type to hold the result of scan
ScanResult = namedtuple('ScanResult', 'error,packages,to_relarea,to_vault,remove_always,remove_success')


#
#
#

def scan(scandir, m, all_packages, arch, args):
    homedir = os.path.join(scandir, m.name)
    basedir = os.path.join(homedir, arch)

    packages = defaultdict(package.Package)
    move = MoveList(homedir)
    vault = MoveList()
    remove = []
    remove_success = []
    error = False
    mtimes = [('', 0)]
    ignored = 0

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
    for (dirpath, _subdirs, files) in os.walk(os.path.join(basedir, 'release')):
        relpath = os.path.relpath(dirpath, homedir)
        removed_files = []

        # filter out files we don't need to consider
        for f in sorted(files):
            if f.endswith('.bak'):
                files.remove(f)

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

        # only process files newer than !ready
        for f in sorted(files):
            fn = os.path.join(dirpath, f)
            file_mtime = os.path.getmtime(fn)
            if file_mtime > mtime:
                if mtime == 0:
                    m.reminders_timestamp_checked = True

                    logging.debug("ignoring %s as there is no !ready" % fn)

                    # don't warn until file is at least REMINDER_GRACE old
                    if (file_mtime < (time.time() - REMINDER_GRACE)):
                        ignored += 1
                else:
                    logging.warning("ignoring %s as it is newer than !ready" % fn)
                files.remove(f)

        # any file remaining?
        if not files:
            continue

        # package doesn't appear in package list at all
        (_, _, pkgpath) = relpath.split(os.sep, 2)
        if not package.is_in_package_list(pkgpath, all_packages):
            logging.error("package '%s' is not in the package list" % relpath)
            continue

        # only process packages for which we are listed as a maintainer
        if not package.is_in_package_list(pkgpath, m.pkgs):
            logging.warning("package '%s' is not in the package list for maintainer '%s'" % (relpath, m.name))
            continue

        # see if we can fix-up any setup.hint files
        pvr = None
        ambiguous = False
        seen = False

        for f in sorted(files):
            # warn about legacy setup.hint uploads
            if f == 'setup.hint':
                logging.warning("'%s' seen, please update to cygport >= 0.23.0" % f)
                seen = True

            match = re.match(r'^([^-].*?)(-src|)\.tar' + common_constants.PACKAGE_COMPRESSIONS_RE + r'$', f)
            if match:
                if (pvr is not None) and (pvr != match.group(1)):
                    ambiguous = True

                pvr = match.group(1)

        if seen:
            if ambiguous or (pvr is None):
                error = True
                logging.error("'setup.hint' seen in %s, and couldn't determine what version it applies to", dirpath)
            else:
                old = "setup.hint"
                new = pvr + ".hint"
                logging.warning("renaming '%s' to '%s'" % (old, new))
                os.rename(os.path.join(dirpath, old), os.path.join(dirpath, new))
                files.remove(old)
                files.append(new)

        for f in sorted(files):
            match = re.match(r'^([^-].*)-src\.tar' + common_constants.PACKAGE_COMPRESSIONS_RE + r'$', f)
            if match:
                pvr = match.group(1)
                old = pvr + '.hint'
                new = pvr + '-src.hint'
                # see if we can fix-up missing -src.hint file
                if (old in files) and (new not in files):
                    logging.warning("copying '%s' to '%s'" % (old, new))
                    shutil.copy2(os.path.join(dirpath, old), os.path.join(dirpath, new))
                    files.append(new)
                    if f.replace('-src', '') not in files:
                        logging.info("discarding '%s'" % (old))
                        files.remove(old)
                        remove.append(os.path.join(dirpath, old))

                # see if we can fix-up missing homepage: in -src.hint file
                # check homepage: for liveliness and redirection
                # discard any keys which are invalid in a -src.hint
                if (new in files):
                    fixes.fix_hint(dirpath, new, f, ['homepage', 'invalid_keys'])

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

            # a remove file, which indicates some other file should be removed
            if f.startswith('-'):
                if ('*' in f) or ('?' in f):
                    logging.error("remove file %s name contains metacharacters, which are no longer supported" % fn)
                    error = True
                elif os.path.getsize(fn) != 0:
                    logging.error("remove file %s is not empty" % fn)
                    error = True
                else:
                    vault.add(relpath, f[1:])
                    remove_success.append(fn)
                    removed_files.append(f[1:])
                files.remove(f)
                continue

            # verify compressed archive files are valid
            match = re.search(r'\.tar' + common_constants.PACKAGE_COMPRESSIONS_RE + r'$', f)
            if match:
                valid = True

                try:
                    # we need to extract all of an archive contents to validate
                    # it
                    with xtarfile.open(fn, mode='r') as a:
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
                        logging.info("discarding, identical %s is already in release area" % fn)
                        remove_success.append(fn)
                    else:
                        logging.error("discarding, different %s is already in release area (perhaps you should rebuild with a different version-release identifier?)" % fn)
                        remove.append(fn)
                        error = True
                    files.remove(f)
                else:
                    if filecmp.cmp(dest, fn, shallow=False):
                        logging.debug("identical %s is already in release area" % fn)
                    else:
                        logging.debug("different %s is already in release area" % fn)
                    # we always consider .hint files as needing to be moved, as
                    # we currently can't have a valid package without one
                    move.add(relpath, f)
            else:
                move.add(relpath, f)

        # read and validate package
        if files:
            if package.read_package_dir(packages, homedir, dirpath, files, remove=removed_files, upload=True):
                error = True

    # always consider timestamp as checked during a dry-run, so it is never
    # reset
    if args.dryrun:
        m.reminders_timestamp_checked = True

    # if files are being ignored, and more than REMINDER_INTERVAL has elapsed
    # since we warned about files being ignored, warn again
    if ignored > 0:
        if (time.time() > (m.reminder_time + REMINDER_INTERVAL)):
            logging.warning("ignored %d files in %s as there is no !ready" % (ignored, arch))
            if not args.dryrun:
                m.reminders_issued = True

    return ScanResult(error, packages, move, vault, remove, remove_success)


#
#
#

def remove(args, remove):
    for f in remove:
        logging.debug("rm %s", f)
        if not args.dryrun:
            try:
                os.unlink(f)
            except FileNotFoundError:
                logging.error("%s can't be deleted as it doesn't exist" % (f))

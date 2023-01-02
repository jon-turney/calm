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
# calm - better than being upset
#

#
# for each arch
# - read and validate packages from release area
# - stop if there are errors
# otherwise,
# identify and move stale packages
# for each maintainer
# - read and validate any package uploads
# - build a list of files to move and remove
# - for each arch
# -- merge package sets
# -- remove from the package set files which are to be removed
# -- validate merged package set
# -- identify stale packages
# -- process remove list
# - on failure
# -- mail maintainer with errors
# -- empty move list
# -- discard merged package sets
# - on success
# -- process move lists
# -- mail maintainer with movelist
# -- continue with merged package sets
# write package listings
# write setup.ini file
#

import argparse
import functools
import logging
import lzma
import os
import shutil
import signal
import sys
import tempfile
import time

from . import common_constants
from . import db
from . import irk
from . import logfilters
from . import maintainers
from . import package
from . import pkg2html
from . import repology
from . import reports
from . import setup_exe
from . import uploads
from . import utils
from .abeyance_handler import AbeyanceHandler
from .buffering_smtp_handler import BufferingSMTPHandler
from .movelist import MoveList


#
#
#

class CalmState(object):
    def __init__(self):
        self.subject = ''
        self.packages = {}
        self.valid_provides = set()
        self.missing_obsolete = {}


#
#
#

def process_relarea(args, state):
    packages = {}
    error = False

    # read the package list for each arch
    for arch in common_constants.ARCHES:
        logging.debug("reading existing packages for arch %s" % (arch))
        packages[arch] = package.read_packages(args.rel_area, arch)

    state.valid_provides = db.update_package_names(args, packages)
    for arch in common_constants.ARCHES:
        state.missing_obsolete[arch] = package.upgrade_oldstyle_obsoletes(packages[arch])

    # validate the package set for each arch
    for arch in common_constants.ARCHES:
        if not package.validate_packages(args, packages[arch], state.valid_provides, state.missing_obsolete[arch]):
            logging.error("existing %s package set has errors" % (arch))
            error = True

    if error:
        return None

    # packages can be stale due to changes made directly in the release
    # area, so first check here if there are any stale packages to vault
    if args.stale:
        stale_to_vault = remove_stale_packages(args, packages, state)
        if stale_to_vault:
            for arch in common_constants.ARCHES + ['noarch', 'src']:
                logging.info("vaulting %d old package(s) for arch %s" % (len(stale_to_vault[arch]), arch))
                stale_to_vault[arch].move_to_vault(args)
        else:
            logging.error("error while evaluating stale packages")
            return None

    # clean up any empty directories
    if not args.dryrun:
        utils.rmemptysubdirs(args.rel_area)

    return packages


#
#
#


def process_uploads(args, state):
    # read maintainer list
    mlist = maintainers.read(args, getattr(args, 'orphanmaint', None))

    # make the list of all packages
    all_packages = maintainers.all_packages(mlist)

    # for each maintainer
    for name in sorted(mlist.keys()):
        m = mlist[name]

        with logfilters.AttrFilter(maint=m.name):
            process_maintainer_uploads(args, state, all_packages, m, args.homedir, 'upload')
            process_maintainer_uploads(args, state, all_packages, m, args.stagingdir, 'staging')

    # record updated reminder times for maintainers
    maintainers.update_reminder_times(mlist)

    return state.packages


def process_maintainer_uploads(args, state, all_packages, m, basedir, desc):
    name = m.name

    # for each arch and noarch
    scan_result = {}
    skip_maintainer = False
    for arch in common_constants.ARCHES + ['noarch', 'src'] + common_constants.ARCHIVED_ARCHES:
        logging.debug("reading uploaded arch %s packages from maintainer %s" % (arch, name))

        # read uploads
        scan_result[arch] = uploads.scan(basedir, m, all_packages, arch, args)

        # remove triggers
        uploads.remove(args, scan_result[arch].remove_always)

        if scan_result[arch].error:
            logging.error("error while reading uploaded arch %s packages from maintainer %s" % (arch, name))
            skip_maintainer = True
            continue

    # if there are no added or removed files for this maintainer, we
    # don't have anything to do
    if not any([scan_result[a].to_relarea or scan_result[a].to_vault for a in scan_result]):
        logging.debug("nothing to do for maintainer %s" % (name))
        skip_maintainer = True

    if skip_maintainer:
        return

    # for each arch
    merged_packages = {}
    valid = True
    for arch in common_constants.ARCHES:
        logging.debug("merging %s package set with uploads from maintainer %s" % (arch, name))

        # merge package sets
        merged_packages[arch] = package.merge(state.packages[arch], scan_result[arch].packages, scan_result['noarch'].packages, scan_result['src'].packages)
        if not merged_packages[arch]:
            logging.error("error while merging uploaded %s packages for %s" % (arch, name))
            valid = False
            break

        # remove files which are to be removed
        scan_result[arch].to_vault.map(lambda p, f: package.delete(merged_packages[arch], p, f))

    # validate the package set
    state.valid_provides = db.update_package_names(args, merged_packages)
    for arch in common_constants.ARCHES:
        logging.debug("validating merged %s package set for maintainer %s" % (arch, name))
        if not package.validate_packages(args, merged_packages[arch], state.valid_provides, state.missing_obsolete):
            logging.error("error while validating merged %s packages for %s" % (arch, name))
            valid = False

    # if an error occurred ...
    if not valid:
        # ... discard move list and merged_packages
        return

    # check for packages which are stale as a result of this upload,
    # which we will want in the same report
    if args.stale:
        stale_to_vault = remove_stale_packages(args, merged_packages, state)

        # if an error occurred ...
        if not stale_to_vault:
            # ... discard move list and merged_packages
            logging.error("error while evaluating stale packages for %s" % (name))
            return

    # check for conflicting movelists
    conflicts = False
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        conflicts = conflicts or report_movelist_conflicts(scan_result[arch].to_relarea, scan_result[arch].to_vault, "manually")
        if args.stale:
            conflicts = conflicts or report_movelist_conflicts(scan_result[arch].to_relarea, stale_to_vault[arch], "automatically")

    # if an error occurred ...
    if conflicts:
        # ... discard move list and merged_packages
        logging.error("error while validating movelists for %s" % (name))
        return

    # for each arch and noarch
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        logging.debug("moving %s packages for maintainer %s" % (arch, name))

        # process the move lists
        if scan_result[arch].to_vault:
            logging.info("vaulting %d package(s) for arch %s, by request" % (len(scan_result[arch].to_vault), arch))
        scan_result[arch].to_vault.move_to_vault(args)
        uploads.remove(args, scan_result[arch].remove_success)
        if scan_result[arch].to_relarea:
            logging.info("adding %d package(s) for arch %s" % (len(scan_result[arch].to_relarea), arch))
        scan_result[arch].to_relarea.move_to_relarea(m, args, desc)
        # XXX: Note that there seems to be a separate process, not run
        # from cygwin-admin's crontab, which changes the ownership of
        # files in the release area to cyguser:cygwin

    # for each arch
    if args.stale:
        for arch in common_constants.ARCHES + ['noarch', 'src']:
            if stale_to_vault[arch]:
                logging.info("vaulting %d old package(s) for arch %s" % (len(stale_to_vault[arch]), arch))
                stale_to_vault[arch].move_to_vault(args)

    # for each arch
    for arch in common_constants.ARCHES:
        # use merged package list
        state.packages[arch] = merged_packages[arch]

    # clean up any empty directories
    if not args.dryrun:
        utils.rmemptysubdirs(os.path.join(basedir, m.name))

    # report what we've done
    added = []
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        added.append('%d (%s)' % (len(scan_result[arch].packages), arch))
    msg = "added %s packages from maintainer %s" % (' + '.join(added), name)
    logging.debug(msg)
    irk.irk("calm %s" % msg)


#
#
#

def process(args, state):
    # send one email per run to leads, if any errors occurred
    with mail_logs(state):
        if args.dryrun:
            logging.warning("--dry-run is in effect, nothing will really be done")

        state.packages = process_relarea(args, state)
        if not state.packages:
            return None

        state.packages = process_uploads(args, state)

    return state.packages


#
# remove stale packages
#

def remove_stale_packages(args, packages, state):
    to_vault = {}
    to_vault['noarch'] = MoveList()
    to_vault['src'] = MoveList()

    for arch in common_constants.ARCHES:
        logging.debug("checking for stale packages for arch %s" % (arch))

        # find stale packages
        to_vault[arch] = package.stale_packages(packages[arch])

        # remove stale packages from package set
        to_vault[arch].map(lambda p, f: package.delete(packages[arch], p, f))

    # if there are no stale packages, we don't have anything to do
    if not any([to_vault[a] for a in to_vault]):
        logging.debug("nothing is stale")
        return to_vault

    # re-validate package sets
    # (this shouldn't fail, but we check just to sure...)
    error = False
    state.valid_provides = db.update_package_names(args, packages)
    for arch in common_constants.ARCHES:
        if not package.validate_packages(args, packages[arch], state.valid_provides, state.missing_obsolete):
            logging.error("%s package set has errors after removing stale packages" % arch)
            error = True

    if error:
        return None

    # since noarch and src packages are included in the package set for both
    # arch, we will build (hopefully) identical move lists for those packages
    # for each arch.
    #
    # de-duplicate these package moves, as rather awkward workaround for that
    moved_list = set()

    def dedup(path, f):
        for prefix in ['noarch', 'src']:
            if path.startswith(prefix):
                to_vault[prefix].add(path, f)
                moved_list.add(path)

    to_vault[common_constants.ARCHES[0]].map(dedup)

    for path in moved_list:
        for arch in common_constants.ARCHES:
            to_vault[arch].remove(path)

    return to_vault


#
# report movelist conflicts
#

def report_movelist_conflicts(a, b, reason):
    conflicts = False

    n = MoveList.intersect(a, b)
    if n:
        def report_conflict(p, f):
            logging.error("%s/%s is both uploaded and %s vaulted" % (p, f, reason))

        n.map(report_conflict)
        conflicts = True

    return conflicts


#
#
#

def do_main(args, state):
    # read package set and process uploads
    packages = process(args, state)

    if not packages:
        logging.error("not processing uploads or writing setup.ini")
        return 1

    state.packages = packages

    do_output(args, state)

    return 0


#
#
#

def do_output(args, state):
    # update packages listings
    # XXX: perhaps we need a --[no]listing command line option to disable this from being run?
    pkg2html.update_package_listings(args, state.packages)

    update_json = False

    # for each arch
    for arch in common_constants.ARCHES:
        logging.debug("writing setup.ini for arch %s" % (arch))

        args.arch = arch
        args.setup_version = setup_exe.extract_version(os.path.join(args.setupdir, 'setup-' + args.arch + '.exe'))
        logging.debug("setup version is '%s'" % (args.setup_version))

        basedir = os.path.join(args.rel_area, args.arch)
        inifile = os.path.join(basedir, 'setup.ini')

        # write setup.ini to a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            args.inifile = tmpfile.name

            changed = False

            # write setup.ini
            package.write_setup_ini(args, state.packages[arch], arch)

            # make it world-readable, if we can
            try:
                os.chmod(args.inifile, 0o644)
            except (OSError):
                pass

            if not os.path.exists(inifile):
                # if the setup.ini file doesn't exist yet
                logging.warning('no existing %s' % (inifile))
                changed = True
            else:
                # or, if it's changed in more than timestamp and comments
                status = os.system('/usr/bin/diff -I^setup-timestamp -I^# -w -B -q %s %s >/dev/null' % (inifile, tmpfile.name))
                logging.debug('diff exit status %d' % (status))
                if (status >> 8) == 1:
                    changed = True

            # then update setup.ini
            if changed:
                update_json = True

                if args.dryrun:
                    logging.warning("not moving %s to %s, due to --dry-run" % (tmpfile.name, inifile))
                    os.remove(tmpfile.name)
                else:
                    # make a backup of the current setup.ini
                    if os.path.exists(inifile):
                        shutil.copy2(inifile, inifile + '.bak')

                    # replace setup.ini
                    logging.info("moving %s to %s" % (tmpfile.name, inifile))
                    shutil.move(tmpfile.name, inifile)
                    irk.irk("calm updated setup.ini for arch '%s'" % (arch))

                    # compress and re-sign
                    extensions = ['.ini', '.bz2', '.xz', '.zst']
                    for ext in extensions:
                        extfile = os.path.join(basedir, 'setup' + ext)
                        try:
                            os.remove(extfile + '.sig')
                        except FileNotFoundError:
                            pass

                        if ext == '.bz2':
                            utils.system('/usr/bin/bzip2 <%s >%s' % (inifile, extfile))
                        elif ext == '.xz':
                            utils.system('/usr/bin/xz -6e <%s >%s' % (inifile, extfile))
                        elif ext == '.zst':
                            utils.system('/usr/bin/zstd -q -f --ultra -20 %s -o %s' % (inifile, extfile))

                        keys = ' '.join(['-u' + k for k in args.keys])
                        utils.system('/usr/bin/gpg ' + keys + ' --batch --yes -b ' + extfile)

            else:
                logging.debug("removing %s, unchanged %s" % (tmpfile.name, inifile))
                os.remove(tmpfile.name)

    # write packages.json
    jsonfile = os.path.join(args.htdocs, 'packages.json.xz')
    if update_json or not os.path.exists(jsonfile):
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmpfile:
            logging.debug('writing %s' % (tmpfile.name))
            with lzma.open(tmpfile, 'wt') as lzf:
                package.write_repo_json(args, state.packages, lzf)
        logging.info("moving %s to %s" % (tmpfile.name, jsonfile))
        shutil.move(tmpfile.name, jsonfile)

        # make it world-readable, if we can
        try:
            os.chmod(jsonfile, 0o644)
        except (OSError):
            pass

    # write reports
    if (update_json or args.force) and args.reports:
        repology.annotate_packages(args, state.packages)
        reports.do_reports(args, state.packages)

    # if we are daemonized, allow force regeneration of static content in htdocs
    # initially (in case the generation code has changed), but update that
    # static content only as needed on subsequent loops
    args.force = 0


#
# daemonization loop
#

def do_daemon(args, state):
    import daemon
    import lockfile.pidlockfile

    context = daemon.DaemonContext(
        stdout=sys.stdout,
        stderr=sys.stderr,
        umask=0o002,
        pidfile=lockfile.pidlockfile.PIDLockFile(args.daemon))

    running = True
    read_relarea = True
    read_uploads = True
    last_signal = None

    # signals! the first, and best, interprocess communications mechanism! :)
    def sigusr1(signum, frame):
        logging.debug("SIGUSR1")
        nonlocal last_signal
        last_signal = signum
        nonlocal read_uploads
        read_uploads = True

    def sigusr2(signum, frame):
        logging.debug("SIGUSR2")
        nonlocal last_signal
        last_signal = signum
        nonlocal read_relarea
        read_relarea = True

    def sigalrm(signum, frame):
        logging.debug("SIGALRM")
        nonlocal last_signal
        last_signal = signum
        nonlocal read_relarea
        read_relarea = True
        nonlocal read_uploads
        read_uploads = True

    def sigterm(signum, frame):
        logging.debug("SIGTERM")
        nonlocal running
        running = False

    context.signal_map = {
        signal.SIGUSR1: sigusr1,
        signal.SIGUSR2: sigusr2,
        signal.SIGALRM: sigalrm,
        signal.SIGTERM: sigterm,
    }

    with context:
        logging_setup(args)
        logging.info("calm daemon started, pid %d" % (os.getpid()))
        irk.irk("calm daemon started")

        state.packages = {}

        try:
            while running:
                with mail_logs(state):
                    # re-read relarea on SIGALRM or SIGUSR2
                    if read_relarea:
                        if last_signal != signal.SIGALRM:
                            irk.irk("calm processing release area")
                        read_relarea = False
                        state.packages = process_relarea(args, state)

                    if not state.packages:
                        logging.error("errors in relarea, not processing uploads or writing setup.ini")
                    else:
                        if read_uploads:
                            if last_signal != signal.SIGALRM:
                                irk.irk("calm processing uploads")
                            # read uploads on SIGUSR1
                            read_uploads = False
                            state.packages = process_uploads(args, state)

                        do_output(args, state)

                        # if there is more work to do, but don't spin if we
                        # can't do anything because relarea is bad
                        if read_uploads:
                            continue

                    # if there is more work to do
                    if read_relarea:
                        continue

                # we wake at a 10 minute offset from the next 240 minute boundary
                # (i.e. at :10 past every fourth hour) to check the state of the
                # release area, in case someone has ninja-ed in a change there...
                interval = 240 * 60
                offset = 10 * 60
                delay = interval - ((time.time() - offset) % interval)
                signal.alarm(int(delay))

                # wait until interrupted by a signal
                if last_signal != signal.SIGALRM:
                    irk.irk("calm processing done")
                logging.info("sleeping for %d seconds" % (delay))
                signal.pause()
                logging.info("woken")

                # cancel any pending alarm
                signal.alarm(0)
        except Exception as e:
            with BufferingSMTPHandler(toaddrs=args.email, subject='calm stopping due to unhandled exception'):
                logging.error("exception %s" % (type(e).__name__), exc_info=True)
            irk.irk("calm daemon stopped due to unhandled exception")
        else:
            irk.irk("calm daemon stopped")

        logging.info("calm daemon stopped")


def mail_logs(state):
    return AbeyanceHandler(functools.partial(mail_cb, state), logging.INFO)


def mail_cb(state, loghandler):
    # we only want to mail the logs if the email option was used
    if not state.args.email:
        return

    # if there are any log records of ERROR level or higher, send those records
    # to leads
    if any([record.levelno >= logging.ERROR for record in loghandler.buffer]):
        leads_email = BufferingSMTPHandler(state.args.email, subject='%s' % (state.subject))
        for record in loghandler.buffer:
            if record.levelno >= logging.ERROR:
                leads_email.handle(record)
        leads_email.close()

    # send each maintainer mail containing log entries caused by their actions,
    # or pertaining to their packages
    mlist = maintainers.read(state.args, prev_maint=False)
    for m in mlist.values():
        email = m.email
        if m.name == 'ORPHANED':
            email = common_constants.EMAILS.split(',')

        if state.args.email == ['debug']:
            email = ['debug']

        maint_email = BufferingSMTPHandler(email, subject='%s for %s' % (state.subject, m.name))
        threshold = logging.WARNING if m.quiet else logging.INFO

        # if there are any log records of thresholdLevel or higher ...
        if any([record.levelno >= threshold for record in loghandler.buffer]):
            # ... send all associated records to the maintainer
            for record in loghandler.buffer:
                if ((getattr(record, 'maint', None) == m.name) or
                    (getattr(record, 'package', None) in m.pkgs)):
                    maint_email.handle(record)

        maint_email.close()


#
# setup logging configuration
#

def logging_setup(args):
    # set up logging to a file
    utils.makedirs(args.logdir)
    rfh = logging.handlers.TimedRotatingFileHandler(os.path.join(args.logdir, 'calm.log'), backupCount=48, when='midnight')
    rfh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)-8s - %(message)s'))
    rfh.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(rfh)

    # setup logging to stdout, of WARNING messages or higher (INFO if verbose)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter(os.path.basename(sys.argv[0]) + ': %(message)s'))
    if args.verbose:
        ch.setLevel(logging.INFO)
    else:
        ch.setLevel(logging.WARNING)
    logging.getLogger().addHandler(ch)

    # change root logger level from the default of WARNING to NOTSET so it
    # doesn't filter out any log messages due to level
    logging.getLogger().setLevel(logging.NOTSET)


#
#
#

def main():
    htdocs_default = os.path.join(common_constants.HTDOCS, 'packages')
    homedir_default = common_constants.HOMEDIR
    stagingdir_default = common_constants.STAGINGDIR
    orphanmaint_default = common_constants.ORPHANMAINT
    pidfile_default = '/sourceware/cygwin-staging/calm.pid'
    pkglist_default = common_constants.PKGMAINT
    relarea_default = common_constants.FTP
    setupdir_default = common_constants.HTDOCS
    vault_default = common_constants.VAULT
    logdir_default = '/sourceware/cygwin-staging/logs'

    parser = argparse.ArgumentParser(description='Upset replacement')
    parser.add_argument('-d', '--daemon', action='store', nargs='?', const=pidfile_default, help="daemonize (PIDFILE defaults to " + pidfile_default + ")", metavar='PIDFILE')
    parser.add_argument('--email', action='store', dest='email', nargs='?', const=common_constants.EMAILS, help="email output to maintainer and ADDRS (ADDRS defaults to '" + common_constants.EMAILS + "')", metavar='ADDRS')
    parser.add_argument('--force', action='count', help="force regeneration of static htdocs content", default=0)
    parser.add_argument('--homedir', action='store', metavar='DIR', help="maintainer home directory (default: " + homedir_default + ")", default=homedir_default)
    parser.add_argument('--htdocs', action='store', metavar='DIR', help="htdocs output directory (default: " + htdocs_default + ")", default=htdocs_default)
    parser.add_argument('--key', action='append', metavar='KEYID', help="key to use to sign setup.ini", default=[], dest='keys')
    parser.add_argument('--logdir', action='store', metavar='DIR', help="log directory (default: '" + logdir_default + "')", default=logdir_default)
    parser.add_argument('--orphanmaint', action='store', metavar='NAMES', help="orphan package maintainers (default: '" + orphanmaint_default + "')", default=orphanmaint_default)
    parser.add_argument('--pkglist', action='store', metavar='FILE', help="package maintainer list (default: " + pkglist_default + ")", default=pkglist_default)
    parser.add_argument('--release', action='store', help='value for setup-release key (default: cygwin)', default='cygwin')
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    parser.add_argument('--setupdir', action='store', metavar='DIR', help="setup executable directory (default: " + setupdir_default + ")", default=setupdir_default)
    parser.add_argument('--stagingdir', action='store', metavar='DIR', help="automated build staging directory (default: " + stagingdir_default + ")", default=stagingdir_default)
    parser.add_argument('--no-stale', action='store_false', dest='stale', help="don't vault stale packages")
    parser.set_defaults(stale=True)
    parser.add_argument('--reports', action='store_true', dest='reports', help="produce reports (default: off unless daemonized)", default=None)
    parser.add_argument('-n', '--dry-run', action='store_true', dest='dryrun', help="don't do anything")
    parser.add_argument('--vault', action='store', metavar='DIR', help="vault directory (default: " + vault_default + ")", default=vault_default, dest='vault')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output')
    (args) = parser.parse_args()

    if args.email:
        args.email = args.email.split(',')

    if args.reports is None:
        args.reports = args.daemon

    state = CalmState()
    state.args = args

    host = os.uname()[1]
    if 'sourceware.org' not in host:
        host = ' from ' + host
    else:
        host = ''
    state.subject = 'calm%s: cygwin package report%s' % (' [dry-run]' if args.dryrun else '', host)

    status = 0
    if args.daemon:
        do_daemon(args, state)
    else:
        logging_setup(args)
        status = do_main(args, state)

    return status


#
#
#

if __name__ == "__main__":
    sys.exit(main())

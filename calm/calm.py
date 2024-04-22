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
import codecs
import functools
import logging
import lzma
import os
import shutil
import signal
import sys
import tempfile
import time
from enum import Flag, auto, unique

import xtarfile

from . import common_constants
from . import db
from . import irk
from . import logfilters
from . import maintainers
from . import package
from . import pkg2html
from . import repology
from . import reports
from . import scallywag_db
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
        packages[arch], _ = package.read_packages(args.rel_area, arch)

    state.valid_provides = db.update_package_names(args, packages)
    for arch in common_constants.ARCHES:
        state.missing_obsolete[arch] = db.update_missing_obsolete(args, packages, arch)

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
        fresh_packages = {}
        for arch in common_constants.ARCHES:
            fresh_packages[arch] = package.merge(packages[arch])

        stale_to_vault = remove_stale_packages(args, fresh_packages, state)
        if stale_to_vault:
            for arch in common_constants.ARCHES + ['noarch', 'src']:
                logging.info("vaulting %d old package(s) for arch %s" % (len(stale_to_vault[arch]), arch))
                stale_to_vault[arch].move_to_vault(args)
        else:
            logging.error("error while evaluating stale packages")
            return None

        packages = fresh_packages

    # clean up any empty directories
    if not args.dryrun:
        utils.rmemptysubdirs(args.rel_area)

    return packages


#
#
#


def process_uploads(args, state):
    # read maintainer list
    mlist = maintainers.maintainer_list(args)

    # make the list of all packages
    all_packages = maintainers.all_packages(args.pkglist)

    # for each maintainer
    for name in sorted(mlist.keys()):
        m = mlist[name]

        with logfilters.AttrFilter(maint=m.name):
            process_maintainer_uploads(args, state, all_packages, m, args.homedir, 'upload')

    # for each deploy job
    def deploy_upload(r):
        m = mlist[r.user]
        with logfilters.AttrFilter(maint=m.name):
            return process_maintainer_uploads(args, state, all_packages, m, os.path.join(args.stagingdir, str(r.id)), 'staging', scrub=True, record=r)

    scallywag_db.do_deploys(deploy_upload)

    # record updated reminder times for maintainers
    maintainers.update_reminder_times(mlist)

    return state.packages


def process_maintainer_uploads(args, state, all_packages, m, basedir, desc, scrub=False, record=None):
    # for each arch and noarch
    scan_result = {}
    success = True
    for arch in common_constants.ARCHES + ['noarch', 'src'] + common_constants.ARCHIVED_ARCHES:
        logging.debug("reading uploaded arch %s packages from maintainer %s" % (arch, m.name))

        # read uploads
        scan_result[arch] = uploads.scan(basedir, m, all_packages, arch, args)

        # remove triggers
        uploads.remove(args, scan_result[arch].remove_always)

        # check upload is authorized
        if not scan_result[arch].error:
            uploads.auth_check(args, m, scan_result[arch], state.packages)

        if scan_result[arch].error:
            logging.error("error while reading uploaded arch %s packages from maintainer %s" % (arch, m.name))
            success = False
            continue

    if success:
        success = _process_maintainer_uploads(scan_result, args, state, all_packages, m, basedir, desc)

    # automatically generate announce email if requested
    if record and success and any([scan_result[a].to_relarea for a in scan_result]):
        _announce_upload(args, scan_result, m, record)

    # remove upload files on success in homedir, always in stagingdir
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        if scrub or success:
            uploads.remove(args, scan_result[arch].remove_success)

    # clean up any empty directories
    if not args.dryrun:
        if scrub:
            utils.rmemptysubdirs(os.path.join(basedir, m.name), depth=0)
        else:
            utils.rmemptysubdirs(os.path.join(basedir, m.name))

    return success


def _announce_upload(args, scan_result, maintainer, r):
    announce = ('announce' in r.tokens) and ('noannounce' not in r.tokens)

    if not announce:
        return

    srcpkg = None
    pkglist = set()
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        for po in scan_result[arch].packages.values():
            if po.kind == package.Kind.source:
                srcpkg = po
                assert len(po.versions()) == 1
                version = list(po.versions())[0]
                ldesc = po.version_hints[version]['ldesc'].strip('"')
                test = 'test' in po.version_hints[version]

            pkglist.add(po.orig_name)

    if not srcpkg:
        logging.error("could not locate source package in upload")
        return
    logging.debug("source package is %s, version %s, test %s", srcpkg.orig_name, version, test)

    # find source tarfile for this particular package version
    to = srcpkg.tar(version)
    tf = to.repopath.abspath(args.rel_area)

    if r.announce:
        # use announce message extracted from cygport, if present
        cl = r.announce
    else:
        # otherwise, look in the source tar file for one of the files we know
        # contains an announce message
        cl = ''
        with xtarfile.open(tf, mode='r') as a:
            files = a.getnames()
            for readme in ['README', srcpkg.orig_name + '.README', 'ANNOUNCE']:
                fn = srcpkg.orig_name + '-' + version + '.src/' + readme
                if fn in files:
                    logging.debug("extracting %s from archive for changelog" % readme)

                    f = codecs.getreader("utf-8")(a.extractfile(fn))

                    # use the contents of an ANNOUNCE file verbatim
                    if readme == 'ANNOUNCE':
                        cl = f.read()
                        break

                    # otherwise, extract relevant part of ChangeLog from README
                    # (between one '---- .* <version> ----' and the next '----' line)
                    found = False
                    for l in f:
                        if not found:
                            if l.startswith('----') and (version in l):
                                cl = l
                                found = True
                        else:
                            if l.startswith('----'):
                                break
                            cl = cl + '\n' + l

                    break

    # TODO: maybe other mechanisms for getting package ChangeLog?
    # NEWS inside upstream source tarball?

    # build the email
    hdr = {}
    hdr['From'] = maintainer.name + ' <cygwin-no-reply@cygwin.com>'
    hdr['Reply-To'] = 'cygwin@cygwin.com'
    hdr['Bcc'] = ','.join(maintainer.email)
    if 'mock' in r.tokens:
        hdr['To'] = hdr['Bcc']
    else:
        hdr['To'] = 'cygwin-announce@cygwin.com'
    hdr['Subject'] = srcpkg.orig_name + ' ' + version + (' (TEST)' if test else '')
    hdr['X-Calm-Announce'] = '1'

    irtid = db.announce_msgid_get(args, srcpkg.orig_name)
    if irtid:
        hdr['In-Reply-To'] = irtid

    msg = '''
The following packages have been uploaded to the Cygwin distribution:

%s

%s

%s

''' % ('\n'.join('* ' + p + '-' + version for p in sorted(pkglist)), ldesc, cl)

    # TODO: add an attachment: sha512 hashes of packages, gpg signed?

    msgid = utils.sendmail(hdr, msg)

    if not irtid:
        db.announce_msgid_set(args, srcpkg.orig_name, msgid)


def _process_maintainer_uploads(scan_result, args, state, all_packages, m, basedir, desc):
    name = m.name

    # if there are no added or removed files for this maintainer, we
    # don't have anything to do
    if not any([scan_result[a].to_relarea or scan_result[a].to_vault for a in scan_result]):
        logging.debug("nothing to do for maintainer %s" % (name))
        return True

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

    # if an error occurred ...
    if not valid:
        # ... discard move list and merged_packages
        return False

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
        return False

    # check for packages which are stale as a result of this upload,
    # which we will want in the same report
    if args.stale:
        stale_to_vault = remove_stale_packages(args, merged_packages, state)

        # if an error occurred ...
        if not stale_to_vault:
            # ... discard move list and merged_packages
            logging.error("error while evaluating stale packages for %s" % (name))
            return False

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
        return False

    # for each arch and noarch
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        logging.debug("moving %s packages for maintainer %s" % (arch, name))

        # process the move lists
        if scan_result[arch].to_vault:
            logging.info("vaulting %d package(s) for arch %s, by request" % (len(scan_result[arch].to_vault), arch))
        scan_result[arch].to_vault.move_to_vault(args)

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

    # report what we've done to irc
    added = []
    for arch in common_constants.ARCHES + ['noarch', 'src']:
        added.append('%d (%s)' % (len(scan_result[arch].packages), arch))
    msg = "added %s packages from maintainer %s" % (' + '.join(added), name)
    logging.debug(msg)
    irk.irk("calm %s" % msg)

    return True


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

    vault_requests = db.vault_requests(args)

    for arch in common_constants.ARCHES:
        logging.debug("checking for stale packages for arch %s" % (arch))

        # find stale packages
        to_vault[arch] = package.stale_packages(packages[arch], vault_requests)

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
# verify signing key(s) are available in gpg-agent
#
def is_passphrase_cached(args):
    passphrase_cached = set()

    for k in args.keygrips:
        logging.debug('Querying gpg-agent on keygrip %s' % (k))
        key_details = utils.system("/usr/bin/gpg-connect-agent 'keyinfo %s' /bye" % k)
        for l in key_details.splitlines():
            if l.startswith('S'):
                # check for either PROTECTION='P' and CACHED='1' (passphrase is
                # cached) or PROTECTION='C' (no passphrase)
                keyinfo = l.split()
                if keyinfo[2] == k:
                    if ((keyinfo[7] == 'P' and keyinfo[6] == '1') or
                        keyinfo[7] == 'C'):
                        passphrase_cached.add(k)
                    else:
                        logging.error("Signing key not available")
                        # Provide some help on the necessary runes: start agent
                        # with --allow-preset-passphrase so that the passphrase
                        # preloaded with gpg-preset-passphrase doesn't expire.
                        logging.error("Load it with '/usr/libexec/gpg-preset-passphrase --preset %s' then provide passphrase" % k)
                    break

    # return True if all keys are accessible
    return passphrase_cached == set(args.keygrips)


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
            if not changed:
                logging.debug("removing %s, unchanged %s" % (tmpfile.name, inifile))
                os.remove(tmpfile.name)
            elif not is_passphrase_cached(args):
                logging.debug("removing %s, cannot sign" % (tmpfile.name))
                os.remove(tmpfile.name)
            else:
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

@unique
class Event(Flag):
    read_uploads = auto()
    read_relarea = auto()


def do_daemon(args, state):
    import daemon
    import inotify.adapters
    import lockfile.pidlockfile

    logging.getLogger('inotify.adapters').propagate = False

    def getLogFileDescriptors(logger):
        """Get a list of fds from logger"""
        handles = []
        for handler in logger.handlers:
            handles.append(handler.stream.fileno())
        if logger.parent:
            handles += getLogFileDescriptors(logger.parent)
        return handles

    context = daemon.DaemonContext(
        stdout=sys.stdout,
        stderr=sys.stderr,
        files_preserve=getLogFileDescriptors(logging.getLogger()),
        umask=0o002,
        pidfile=lockfile.pidlockfile.PIDLockFile(args.daemon))

    # XXX: running flag isn't actually doing anything anymore so can be removed
    running = True
    # do all actions initially
    action = Event.read_uploads | Event.read_relarea
    saw_events = False

    def sigterm(signum, frame):
        logging.debug("SIGTERM")
        nonlocal running
        running = False
        raise InterruptedError

    def sighup(signum, frame):
        logging.debug("SIGHUP")

    context.signal_map = {
        signal.SIGTERM: sigterm,
        signal.SIGHUP: sighup,
    }

    with context:
        logging.info("calm daemon started, pid %d" % (os.getpid()))
        irk.irk("calm daemon started")

        state.packages = {}

        # watch for changes in relarea, upload and staging directories
        i = inotify.adapters.InotifyTrees([args.rel_area, args.homedir, args.stagingdir],
                                          mask=inotify.constants.IN_CREATE | inotify.constants.IN_DELETE | inotify.constants.IN_CLOSE_WRITE | inotify.constants.IN_ATTRIB | inotify.constants.IN_MOVED_TO,
                                          block_duration_s=60)

        try:
            while running:
                if action:
                    with mail_logs(state):
                        if Event.read_relarea in action:
                            if saw_events:
                                irk.irk("calm processing release area")
                            state.packages = process_relarea(args, state)

                        if not state.packages:
                            logging.error("errors in relarea, not processing uploads or writing setup.ini")
                        else:
                            if Event.read_uploads in action:
                                if saw_events:
                                    irk.irk("calm processing uploads")
                                state.packages = process_uploads(args, state)

                            do_output(args, state)

                        if saw_events:
                            irk.irk("calm processing done")

                # we wake at a 10 minute offset from the next 240 minute boundary
                # (i.e. at :10 past every fourth hour) to check the state of the
                # release area, in case someone has ninja-ed in a change there...
                interval = 240 * 60
                offset = 10 * 60
                delay = interval - ((time.time() - offset) % interval)
                next_scan_time = time.time() + delay

                if action:
                    logging.info("next rescan in %d seconds" % (delay))

                action = Event(0)
                saw_events = False
                depth = args.rel_area.count(os.path.sep) + 1

                try:
                    # It would be nice to use inotify.adaptor's timeout feature so
                    # we go at least a few seconds without events, to ensure that we
                    # don't start processing in the middle of a flurry of events.
                    # Unfortunately, that goes back to waiting for the full
                    # block_duration_s if timeout hasn't expired...
                    for event in i.event_gen(yield_nones=True):
                        if event is not None:
                            logging.debug("inotify event %s" % str(event))
                            saw_events = True
                            (_, type_names, path, filename) = event
                            if path.startswith(args.rel_area):
                                # ignore sha512.sum and modifications to setup.*
                                # files in the arch directory
                                if (filename != 'sha512.sum') and ((path.count(os.path.sep) > depth) or filename == ".touch"):
                                    action |= Event.read_relarea
                            elif path.startswith(args.stagingdir) and (filename != 'tmp'):
                                action |= Event.read_uploads
                            elif (path.startswith(args.homedir)) and (filename == "!ready"):
                                action |= Event.read_uploads
                        else:
                            # None means no more events are currently available, so
                            # break to process actions
                            break
                except inotify.calls.InotifyError:
                    # can occur if a just created directory is (re)moved before
                    # we set a watch on it
                    pass

                if not saw_events:
                    if time.time() > next_scan_time:
                        logging.debug("scheduled rescan")
                        action |= (Event.read_uploads | Event.read_relarea)

                if action:
                    logging.info("woken, actions %s" % action)

        except InterruptedError:
            # inotify module has the annoying behaviour of eating any EINTR
            # returned by the poll on inotify fd, assuming it's indicating a
            # timeout rather than a signal
            #
            # so we arrange for signals to raise an InterruptedError
            # exception, to pop out here
            stop_reason = "calm daemon stopped by SIGTERM"

        except Exception as e:
            with BufferingSMTPHandler(toaddrs=args.email, subject='calm stopping due to unhandled exception'):
                logging.error("exception %s" % (type(e).__name__), exc_info=True)
            stop_reason = "calm daemon stopped due to unhandled exception"

        else:
            stop_reason = "calm daemon stopped for unknown reason"

        irk.irk(stop_reason)
        logging.info(stop_reason)


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
    mlist = maintainers.maintainer_list(state.args)
    for m in mlist.values():
        # may happen for previous maintainers who orphaned all their packages
        # before an email became mandatory
        if not m.email:
            continue

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
    trustedmaint_default = common_constants.TRUSTEDMAINT
    pidfile_default = '/sourceware/cygwin-staging/lock/calm.pid'
    pkglist_default = common_constants.PKGMAINT
    relarea_default = common_constants.FTP
    repodir_default = '/git/cygwin-packages'
    setupdir_default = common_constants.HTDOCS
    vault_default = common_constants.VAULT
    logdir_default = '/sourceware/cygwin-staging/logs'
    key_default = [common_constants.DEFAULT_GPG_KEY]

    parser = argparse.ArgumentParser(description='Upset replacement')
    parser.add_argument('-d', '--daemon', action='store', nargs='?', const=pidfile_default, help="daemonize (PIDFILE defaults to " + pidfile_default + ")", metavar='PIDFILE')
    parser.add_argument('--email', action='store', dest='email', nargs='?', default='', const=common_constants.EMAILS, help="email output to maintainer and ADDRS (ADDRS defaults to '" + common_constants.EMAILS + "')", metavar='ADDRS')
    parser.add_argument('--force', action='count', help="force regeneration of static htdocs content", default=0)
    parser.add_argument('--homedir', action='store', metavar='DIR', help="maintainer home directory (default: " + homedir_default + ")", default=homedir_default)
    parser.add_argument('--htdocs', action='store', metavar='DIR', help="htdocs output directory (default: " + htdocs_default + ")", default=htdocs_default)
    parser.add_argument('--key', action='append', metavar='KEYID', help="key to use to sign setup.ini", default=key_default, dest='keys')
    parser.add_argument('--logdir', action='store', metavar='DIR', help="log directory (default: '" + logdir_default + "')", default=logdir_default)
    parser.add_argument('--trustedmaint', action='store', metavar='NAMES', help="trusted package maintainers (default: '" + trustedmaint_default + "')", default=trustedmaint_default)
    parser.add_argument('--pkglist', action='store', metavar='FILE', help="package maintainer list (default: " + pkglist_default + ")", default=pkglist_default)
    parser.add_argument('--release', action='store', help='value for setup-release key (default: cygwin)', default='cygwin')
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    parser.add_argument('--repodir', action='store', metavar='DIR', help="packaging repositories directory (default: " + repodir_default + ")", default=repodir_default)
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

    logging_setup(args)

    # find matching keygrips for keys
    args.keygrips = []
    for k in args.keys:
        details = utils.system('gpg2 --list-keys --with-keygrip --with-colons %s' % k)
        for l in details.splitlines():
            if l.startswith('grp'):
                grip = l.split(':')[9]
                args.keygrips.append(grip)
                logging.debug('key ID %s has keygrip %s' % (k, grip))

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
        status = do_main(args, state)

    return status


#
#
#

if __name__ == "__main__":
    sys.exit(main())

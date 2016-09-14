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

from collections import defaultdict
from contextlib import ExitStack
import argparse
import logging
import os
import shutil
import sys
import tempfile

from .abeyance_handler import AbeyanceHandler
from .buffering_smtp_handler import BufferingSMTPHandler
from . import common_constants
from . import maintainers
from . import package
from . import pkg2html
from . import queue
from . import setup_exe
from . import uploads


#
#
#

def process(args):
    subject = 'calm%s: cygwin package upload report from %s' % (' [dry-run]' if args.dryrun else '', os.uname()[1])

    # send one email per run to leads, if any errors occurred
    with mail_logs(args.email, toaddrs=args.email, subject='%s' % (subject), thresholdLevel=logging.ERROR) as leads_email:
        if args.dryrun:
            logging.warning("--dry-run is in effect, nothing will really be done")

        # for each arch
        error = False
        packages = {}
        for arch in common_constants.ARCHES:
            logging.debug("reading existing packages for arch %s" % (arch))

            # build package list
            packages[arch] = package.read_packages(args.rel_area, arch)

            # validate the package set
            if not package.validate_packages(args, packages[arch]):
                logging.error("existing %s package set has errors" % (arch))
                error = True

        if error:
            return None

        # packages can be stale due to changes made directly in the release
        # area, so first check here if there are any stale packages to vault
        if args.stale:
            stale_to_vault = remove_stale_packages(args, packages)
            if stale_to_vault:
                for arch in common_constants.ARCHES + ['noarch']:
                    logging.info("vaulting %d old files for arch %s, which are no longer accessible by installer" % (len(stale_to_vault[arch]), arch))
                    uploads.move_to_vault(args, stale_to_vault[arch])
            else:
                return None

        # read maintainer list
        mlist = maintainers.Maintainer.read(args)

        # make the list of all packages
        all_packages = maintainers.Maintainer.all_packages(mlist)

        # for each maintainer
        for name in sorted(mlist.keys()):
            m = mlist[name]

            # also send a mail to each maintainer about their packages
            with mail_logs(args.email, toaddrs=m.email, subject='%s for %s' % (subject, name), thresholdLevel=logging.INFO) as maint_email:

                # for each arch and noarch
                scan_result = {}
                skip_maintainer = False
                for arch in common_constants.ARCHES + ['noarch']:
                    logging.debug("reading uploaded arch %s packages from maintainer %s" % (arch, name))

                    # read uploads
                    scan_result[arch] = uploads.scan(m, all_packages, arch, args)

                    # remove triggers
                    uploads.remove(args, scan_result[arch].remove_always)

                    if scan_result[arch].error:
                        logging.error("error while reading uploaded arch %s packages from maintainer %s" % (arch, name))
                        skip_maintainer = True
                        continue

                    # queue for source package validator
                    queue.add(args, scan_result[arch].to_relarea, os.path.join(m.homedir()))

                # if there are no uploaded or removed packages for this
                # maintainer, we don't have anything to do
                if not any([scan_result[a].packages or scan_result[a].to_vault for a in scan_result]):
                    logging.debug("nothing to do for maintainer %s" % (name))
                    skip_maintainer = True

                if skip_maintainer:
                    continue

                # for each arch
                merged_packages = {}
                valid = True
                for arch in common_constants.ARCHES:
                    logging.debug("merging %s package set with uploads from maintainer %s" % (arch, name))

                    # merge package sets
                    merged_packages[arch] = package.merge(packages[arch], scan_result[arch].packages, scan_result['noarch'].packages)
                    if not merged_packages[arch]:
                        logging.error("error while merging uploaded %s packages for %s" % (arch, name))
                        valid = False
                        break

                    # remove files which are to be removed
                    for p in scan_result[arch].to_vault:
                        for f in scan_result[arch].to_vault[p]:
                            package.delete(merged_packages[arch], p, f)

                    # validate the package set
                    logging.debug("validating merged %s package set for maintainer %s" % (arch, name))
                    if not package.validate_packages(args, merged_packages[arch]):
                        logging.error("error while validating merged %s packages for %s" % (arch, name))
                        valid = False

                # if an error occurred ...
                if not valid:
                    # ... discard move list and merged_packages
                    continue

                # check for packages which are stale as a result of this upload,
                # which we will want in the same report
                if args.stale:
                    stale_to_vault = remove_stale_packages(args, merged_packages)

                    # if an error occurred ...
                    if not stale_to_vault:
                        # ... discard move list and merged_packages
                        continue

                # check for conflicting movelists
                conflicts = False
                for arch in common_constants.ARCHES + ['noarch']:
                    conflicts = conflicts or report_movelist_conflicts(scan_result[arch].to_relarea, scan_result[arch].to_vault, "manually")
                    if args.stale:
                        conflicts = conflicts or report_movelist_conflicts(scan_result[arch].to_relarea, stale_to_vault[arch], "automatically")

                # if an error occurred ...
                if conflicts:
                    # ... discard move list and merged_packages
                    continue

                # for each arch and noarch
                for arch in common_constants.ARCHES + ['noarch']:
                    logging.debug("moving %s packages for maintainer %s" % (arch, name))

                    # process the move lists
                    uploads.move_to_vault(args, scan_result[arch].to_vault)
                    uploads.remove(args, scan_result[arch].remove_success)
                    uploads.move_to_relarea(m, args, scan_result[arch].to_relarea)

                # for each arch
                if args.stale:
                    for arch in common_constants.ARCHES + ['noarch']:
                        if stale_to_vault[arch]:
                            logging.info("vaulting %d old files for arch %s, which are no longer accessible by installer" % (len(stale_to_vault[arch]), arch))
                            uploads.move_to_vault(args, stale_to_vault[arch])

                # for each arch
                for arch in common_constants.ARCHES:
                    # use merged package list
                    packages[arch] = merged_packages[arch]
                    logging.debug("added %d + %d packages from maintainer %s" % (len(scan_result[arch].packages), len(scan_result['noarch'].packages), name))

        # record updated reminder times for maintainers
        maintainers.Maintainer.update_reminder_times(mlist)

    return packages


#
# remove stale packages
#

def remove_stale_packages(args, packages):
    to_vault = {}
    to_vault['noarch'] = defaultdict(list)

    for arch in common_constants.ARCHES:
        logging.debug("checking for stale packages for arch %s" % (arch))

        # find stale packages
        to_vault[arch] = package.stale_packages(packages[arch])

        # remove stale packages from package set
        for p in to_vault[arch]:
            for f in to_vault[arch][p]:
                package.delete(packages[arch], p, f)

    # if there are no stale packages, we don't have anything to do
    if not any([to_vault[a] for a in to_vault]):
        logging.debug("nothing is stale")
        return to_vault

    # re-validate package sets
    # (this shouldn't fail, but we check just to sure...)
    error = False
    for arch in common_constants.ARCHES:
        if not package.validate_packages(args, packages[arch]):
            logging.error("%s package set has errors after removing stale packages" % arch)
            error = True

    if error:
        return None

    # since noarch packages are included in the package set for both arch, we
    # will build (hopefully) identical move lists for those packages for each
    # arch.
    #
    # de-duplicate these package moves, as rather awkward workaround for that
    for path in list(to_vault[common_constants.ARCHES[0]]):
        if path.startswith('noarch'):
            to_vault['noarch'][path] = to_vault[common_constants.ARCHES[0]][path]
            for arch in common_constants.ARCHES:
                del to_vault[arch][path]

    return to_vault


#
# report movelist conflicts
#

def report_movelist_conflicts(a, b, reason):
    conflicts = False

    n = uploads.movelist_intersect(a, b)
    if n:
        for p in n:
            for f in n[p]:
                logging.error("%s/%s is both uploaded and %s vaulted" % (p, f, reason))
        conflicts = True

    return conflicts


#
#
#

def do_main(args):
    # read package set and process uploads
    packages = process(args)

    if not packages:
        logging.error("not processing uploads or writing setup.ini")
        return

    # for each arch
    for arch in common_constants.ARCHES:
        # update packages listings
        # XXX: perhaps we need a --[no]listing command line option to disable this from being run?
        pkg2html.update_package_listings(args, packages[arch], arch)

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
            package.write_setup_ini(args, packages[arch], arch)

            if not os.path.exists(inifile):
                # if the setup.ini file doesn't exist yet
                logging.warning('no existing %s' % (inifile))
                changed = True
            else:
                # or, if it's changed in more than timestamp
                status = os.system('/usr/bin/diff -I^setup-timestamp -w -B -q %s %s >/dev/null' % (inifile, tmpfile.name))
                logging.debug('diff exit status %d' % (status))
                if (status >> 8) == 1:
                    changed = True

            # then update setup.ini
            if changed:
                if args.dryrun:
                    logging.warning("not moving %s to %s, due to --dry-run" % (tmpfile.name, inifile))
                    os.remove(tmpfile.name)
                else:
                    # make a backup of the current setup.ini
                    shutil.copy2(inifile, inifile + '.bak')

                    # replace setup.ini
                    logging.info("moving %s to %s" % (tmpfile.name, inifile))
                    shutil.move(tmpfile.name, inifile)

                    # compress and re-sign
                    for ext in ['.ini', '.bz2', '.xz']:
                        try:
                            os.remove(os.path.join(basedir, 'setup' + ext + '.sig'))
                        except FileNotFoundError:
                            pass

                        if ext == '.bz2':
                            os.system('/usr/bin/bzip2 <%s >%s' % (inifile, os.path.splitext(inifile)[0] + ext))
                        elif ext == '.xz':
                            os.system('/usr/bin/xz -6e <%s >%s' % (inifile, os.path.splitext(inifile)[0] + ext))

                        os.system('/usr/bin/gpg --batch --yes -b ' + os.path.join(basedir, 'setup' + ext))

                    # arrange for checksums to be recomputed
                    for sumfile in ['md5.sum', 'sha512.sum']:
                        try:
                            os.remove(os.path.join(basedir, sumfile))
                        except FileNotFoundError:
                            pass
            else:
                logging.debug("removing %s, unchanged %s" % (tmpfile.name, inifile))
                os.remove(tmpfile.name)


#
# we only want to mail the logs if the email option was used
# (otherwise use ExitStack() as a 'do nothing' context)
#

def mail_logs(enabled, toaddrs, subject, thresholdLevel, retainLevel=None):
    if enabled:
        return AbeyanceHandler(BufferingSMTPHandler(toaddrs, subject), thresholdLevel, retainLevel)

    return ExitStack()


#
#
#

def main():
    htdocs_default = os.path.join(common_constants.HTDOCS, 'packages')
    homedir_default = common_constants.HOMEDIR
    orphanmaint_default = common_constants.ORPHANMAINT
    pkglist_default = common_constants.PKGMAINT
    relarea_default = common_constants.FTP
    setupdir_default = common_constants.HTDOCS
    vault_default = common_constants.VAULT
    logdir_default = '/sourceware/cygwin-staging/logs'
    queuedir_default = '/sourceware/cygwin-staging/queue'

    parser = argparse.ArgumentParser(description='Upset replacement')
    parser.add_argument('--email', action='store', dest='email', nargs='?', const=common_constants.EMAILS, help='email output to maintainer and ADDRS (default: ' + common_constants.EMAILS + ')', metavar='ADDRS')
    parser.add_argument('--force', action='store_true', help="overwrite existing files")
    parser.add_argument('--homedir', action='store', metavar='DIR', help="maintainer home directory (default: " + homedir_default + ")", default=homedir_default)
    parser.add_argument('--htdocs', action='store', metavar='DIR', help="htdocs output directory (default: " + htdocs_default + ")", default=htdocs_default)
    parser.add_argument('--logdir', action='store', metavar='DIR', help="log directory (default: '" + logdir_default + "')", default=logdir_default)
    parser.add_argument('--orphanmaint', action='store', metavar='NAMES', help="orphan package maintainers (default: '" + orphanmaint_default + "')", default=orphanmaint_default)
    parser.add_argument('--pkglist', action='store', metavar='FILE', help="package maintainer list (default: " + pkglist_default + ")", default=pkglist_default)
    parser.add_argument('--queuedir', action='store', nargs='?', metavar='DIR', help="queue directory (default: '" + queuedir_default + "')", const=queuedir_default)
    parser.add_argument('--release', action='store', help='value for setup-release key (default: cygwin)', default='cygwin')
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    parser.add_argument('--setupdir', action='store', metavar='DIR', help="setup executable directory (default: " + setupdir_default + ")", default=setupdir_default)
    parser.add_argument('--no-stale', action='store_false', dest='stale', help="don't vault stale packages")
    parser.set_defaults(stale=True)
    parser.add_argument('-n', '--dry-run', action='store_true', dest='dryrun', help="don't do anything")
    parser.add_argument('--vault', action='store', metavar='DIR', help="vault directory (default: " + vault_default + ")", default=vault_default, dest='vault')
    parser.add_argument('-v', '--verbose', action='count', dest='verbose', help='verbose output')
    (args) = parser.parse_args()

    # set up logging to a file
    try:
        os.makedirs(args.logdir, exist_ok=True)
    except FileExistsError:
        pass
    rfh = logging.handlers.RotatingFileHandler(os.path.join(args.logdir, 'calm.log'), backupCount=48)
    rfh.doRollover()  # force a rotate on every run
    rfh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)-8s - %(message)s'))
    rfh.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(rfh)

    # setup logging to stdout, of WARNING messages or higher (INFO if verbose)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter(os.path.basename(sys.argv[0])+': %(message)s'))
    if args.verbose:
        ch.setLevel(logging.INFO)
    else:
        ch.setLevel(logging.WARNING)
    logging.getLogger().addHandler(ch)

    # change root logger level from the default of WARNING to NOTSET so it
    # doesn't filter out any log messages due to level
    logging.getLogger().setLevel(logging.NOTSET)

    if args.email:
        args.email = args.email.split(',')

    do_main(args)


#
#
#

if __name__ == "__main__":
    sys.exit(main())

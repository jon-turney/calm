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
# read packages from release area
# for each maintainer
# - read and validate any package uploads
# - build a list of files to move and remove
# - merge package sets
# - remove from the package set files which are to be removed
# - validate merged package set
# - process remove list
# - on failure
# -- mail maintainer with errors
# -- empty move list
# -- discard merged package set
# - on success
# -- process move list
# -- mail maintainer with movelist
# -- continue with merged package set
# write setup.ini file
#

import argparse
import logging
import os
import shutil
import sys
import tempfile

from buffering_smtp_handler import mail_logs
import common_constants
import maintainers
import package
import pkg2html
import setup_exe
import uploads


#
#
#

def process_arch(args):
    details = '%s%s' % (args.arch, ',dry-run' if args.dryrun else '')

    # send one email per run to leads
    with mail_logs(args.email, toaddrs=args.email, subject='calm messages [%s]' % (details)) as leads_email:
        if args.dryrun:
            logging.warning("--dry-run in effect, nothing will really be done")

        # build package list
        packages = package.read_packages(args.rel_area, args.arch)

        # validate the package set
        if not package.validate_packages(args, packages):
            logging.error("existing package set has errors, not processing uploads or writing setup.ini")
            return False

        # read maintainer list
        mlist = maintainers.Maintainer.read(args)

        # make the list of all packages
        all_packages = maintainers.Maintainer.all_packages(mlist)

        # for each maintainer
        for name in sorted(mlist.keys()):
            m = mlist[name]

            # also send a mail to each maintainer about their packages
            with mail_logs(args.email, toaddrs=m.email, subject='calm messages for %s [%s]' % (name, details)) as maint_email:

                (error, mpackages, to_relarea, to_vault, remove_always, remove_success) = uploads.scan(m, all_packages, args)

                uploads.remove(args, remove_always)

                # if there are no uploaded packages for this maintainer, we
                # don't have anything to do
                if not mpackages:
                    logging.info("nothing to do for maintainer %s" % (name))
                    continue

                if not error:
                    # merge package set
                    merged_packages = package.merge(packages, mpackages)

                    # remove file which are to be removed
                    #
                    # XXX: this doesn't properly account for removing setup.hint
                    # files
                    for p in to_vault:
                        for f in to_vault[p]:
                            package.delete(merged_packages, p, f)

                    # validate the package set
                    if package.validate_packages(args, merged_packages):
                        # process the move list
                        uploads.move_to_vault(args, to_vault)
                        uploads.remove(args, remove_success)
                        uploads.move_to_relarea(m, args, to_relarea)
                        # use merged package list
                        packages = merged_packages
                        logging.info("added %d packages from maintainer %s" % (len(mpackages), name))
                    else:
                        # otherwise we discard move list and merged_packages
                        logging.error("error while merging uploaded packages for %s" % (name))

        # write setup.ini
        package.write_setup_ini(args, packages)

        # update packages listings
        # XXX: perhaps we need a --[no]listing command line option to disable this from being run?
        pkg2html.update_package_listings(args, packages)

        return True


#
#
#

def main(args):
    # for each arch
    for arch in common_constants.ARCHES:
        logging.info("processing arch %s" % (arch))

        args.arch = arch
        args.setup_version = setup_exe.extract_version(os.path.join(args.setupdir, 'setup-' + args.arch + '.exe'))
        logging.info("setup version is '%s'" % (args.setup_version))

        basedir = os.path.join(args.rel_area, args.arch)
        inifile = os.path.join(basedir, 'setup.ini')

        # write setup.ini to a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            args.inifile = tmpfile.name

            changed = False
            if not process_arch(args):
                # generating setup.ini failed
                pass
            elif not os.path.exists(inifile):
                # if the setup.ini file doesn't exist yet
                logging.warning('no existing %s' % (inifile))
                changed = True
            else:
                # or, if it's changed in more than timestamp
                status = os.system('/usr/bin/diff -I^setup-timestamp -w -B -q %s %s >/dev/null' % (inifile, tmpfile.name))
                logging.info('diff exit status %d' % (status))
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
                    logging.warning("moving %s to %s" % (tmpfile.name, inifile))
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
                logging.info("removing %s, unchanged %s" % (tmpfile.name, inifile))
                os.remove(tmpfile.name)


#
#
#

if __name__ == "__main__":
    htdocs_default = os.path.join(common_constants.HTDOCS, 'packages')
    homedir_default = common_constants.HOMEDIR
    orphanmaint_default = common_constants.ORPHANMAINT
    pkglist_default = common_constants.PKGMAINT
    relarea_default = common_constants.FTP
    setupdir_default = common_constants.HTDOCS
    vault_default = common_constants.VAULT
    logdir_default = '/sourceware/cygwin-staging/logs'

    parser = argparse.ArgumentParser(description='Upset replacement')
    parser.add_argument('--email', action='store', dest='email', nargs='?', const=common_constants.EMAILS, help='email output to maintainer and ADDRS (default: ' + common_constants.EMAILS + ')', metavar='ADDRS')
    parser.add_argument('--force', action='store_true', help="overwrite existing files")
    parser.add_argument('--homedir', action='store', metavar='DIR', help="maintainer home directory (default: " + homedir_default + ")", default=homedir_default)
    parser.add_argument('--htdocs', action='store', metavar='DIR', help="htdocs output directory (default: " + htdocs_default + ")", default=htdocs_default)
    parser.add_argument('--logdir', action='store', metavar='DIR', help="log directory (default: '" + logdir_default + "')", default=logdir_default)
    parser.add_argument('--orphanmaint', action='store', metavar='NAMES', help="orphan package maintainers (default: '" + orphanmaint_default + "')", default=orphanmaint_default)
    parser.add_argument('--pkglist', action='store', metavar='FILE', help="package maintainer list (default: " + pkglist_default + ")", default=pkglist_default)
    parser.add_argument('--release', action='store', help='value for setup-release key (default: cygwin)', default='cygwin')
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='rel_area')
    parser.add_argument('--setupdir', action='store', metavar='DIR', help="setup executable directory (default: " + setupdir_default + ")", default=setupdir_default)
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
    rfh.setLevel(logging.INFO)
    logging.getLogger().addHandler(rfh)

    # setup logging to stdout, of WARNING messages or higher (INFO if verbose)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter(os.path.basename(sys.argv[0])+': %(message)s'))
    if args.verbose:
        ch.setLevel(logging.INFO)
    else:
        ch.setLevel(logging.WARNING)
    logging.getLogger().addHandler(ch)

    # change root logger level from the default of WARNING
    logging.getLogger().setLevel(logging.INFO)

    if args.email:
        args.email = args.email.split(',')

    sys.exit(main(args))
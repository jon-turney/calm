#!/usr/bin/env python3
#
# Copyright (c) 2024 Jon Turney
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

import argparse
import logging
import os
import sys
import time

from . import common_constants
from . import package
from . import pkg2html
from . import reports
from . import utils

MAINTAINER_ACTIVITY_THRESHOLD_YEARS = 8.5

template = '''
Hi {},

As a part of keeping Cygwin secure, your package maintainer account has been
found to be long inactive. It will soon be disabled and your packages moved to
'ORPHANED' status.

The estimated date of your last packaging activity is {} UTC.

Any action using your ssh key is sufficient to keep your account alive, e.g.:

* do a git pull with an ssh://cygwin@cygwin.com/ URL
* run 'ssh cygwin@cygwin.com alive'

For reference, the list of packages you are recorded as a maintainer of is:

{}

Thanks for all your work on these!

For further assistance, please contact us via email at <cygwin-apps@cygwin.com>

'''


def main(args):
    logging.getLogger().setLevel(logging.WARNING)

    packages = {}
    for arch in common_constants.ARCHES:
        logging.debug("reading existing packages for arch %s" % (arch))
        packages[arch], _ = package.read_packages(args.relarea, arch)

    activity_list = reports.maintainer_activity(args, packages)

    logging.getLogger().setLevel(logging.INFO)

    threshold = time.time() - MAINTAINER_ACTIVITY_THRESHOLD_YEARS * 365.25 * 24 * 60 * 60
    logging.info('threshold date %s', pkg2html.tsformat(threshold))

    for a in activity_list:
        last_activity = max(a.last_seen, a.last_package)

        if last_activity < threshold:
            logging.info('%s %s %s %s', a.name, a.email, pkg2html.tsformat(last_activity), a.pkgs)
            pkg_list = [packages[arch][p].orig_name for p in a.pkgs]

            hdr = {}
            hdr['To'] = ','.join(a.email)
            hdr['From'] = 'cygwin-no-reply@cygwin.com'
            hdr['Envelope-From'] = common_constants.ALWAYS_BCC  # we want to see bounces
            hdr['Reply-To'] = 'cygwin-apps@cygwin.com'
            hdr['Bcc'] = common_constants.ALWAYS_BCC
            hdr['Subject'] = 'upcoming removal of cygwin package maintainer account for %s' % a.name
            hdr['X-Calm-Inactive-Maintainer'] = '1'

            msg = template.format(a.name, pkg2html.tsformat(last_activity), '\n'.join(pkg_list))

            if not args.dryrun:
                msg_id = utils.sendmail(hdr, msg)
                logging.info('%s', msg_id)
            else:
                print(msg)


if __name__ == "__main__":
    relarea_default = common_constants.FTP
    homedir_default = common_constants.HOMEDIR
    pkglist_default = common_constants.PKGMAINT

    parser = argparse.ArgumentParser(description='Send mail to inactive maintainers')
    parser.add_argument('--homedir', action='store', metavar='DIR', help="maintainer home directory (default: " + homedir_default + ")", default=homedir_default)
    parser.add_argument('--pkglist', action='store', metavar='FILE', help="package maintainer list (default: " + pkglist_default + ")", default=pkglist_default)
    parser.add_argument('--releasearea', action='store', metavar='DIR', help="release directory (default: " + relarea_default + ")", default=relarea_default, dest='relarea')
    parser.add_argument('-n', '--dry-run', action='store_true', dest='dryrun', help="don't send mails")

    (args) = parser.parse_args()

    logging.basicConfig(format=os.path.basename(sys.argv[0]) + ': %(message)s')

    main(args)

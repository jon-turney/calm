#
#

#
# things we know about a maintainer:
#
# - their home directory
# - the list of packages they maintain (given by cygwin-pkg-list)
# - an email address (in HOME/!email (or !mail), as we don't want to publish
#   it, and want to allow the maintainer to change it)
#

import os
import re
import sys
import collections
import cygwin

class Maintainer:
    _homedirs = ''

    def __init__(self, name):
        self.name = name
        self.email = ''
        self.pkgs = []

    def homedir(self):
        return os.path.join(Maintainer._homedirs, self.name)

list = collections.defaultdict(Maintainer)

# add maintainers which have existing directories
def add_maintainer_directories(dir=None):
    if dir is None:
        dir = cygwin.HOMEDIRS
    Maintainer._homedirs = dir

    for n in os.listdir(dir):
        m = Maintainer(n)

        for e in ['!email', '!mail'] :
            email = os.path.join(dir, e)
            if os.path.isfile(email):
                with open(email) as f:
                    m.email = f.read()

        list[n] = m

# add maintainers from the package maintainers list, with the packages they
# maintain
def add_maintainer_packages(pkglist=None, orphanMaint=None):
    if pkglist is None:
        pkglist = cygwin.PKGMAINT

    with open(pkglist) as f:
        for (i, l) in enumerate(f):
            l = l.rstrip()

            # match lines of the form '<package> <maintainer(s)>'
            match = re.match(r'^(\S+)\s+(.+)$', l)
            if match:
                pkg = match.group(1)
                m0 = match.group(2)

                # orphaned packages get the default maintainer if we have
                # one, otherwise are ignored
                if m0.startswith('ORPHANED'):
                    if orphanMaint is not None:
                        m0 = orphanMaint
                    else:
                        continue

                # ensure any metacharacters in pkg are escaped
                pkg = re.escape(pkg)

                # joint maintainers are separated by '/'
                for m in m0.split('/'):
                    list[m].pkgs.append(pkg)

            else:
                print("%s: unrecognized line in %s:%d: '%s'" % (sys.argv[0], pkglist, i, l))

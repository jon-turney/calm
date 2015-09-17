#!/usr/bin/env python3
#
# package
#

import os
import re
from collections import defaultdict

import hint
import common_constants

class Package(object):
    def __init__(self):
        self.path = ''
        self.tars = []
        self.hints = {}

def read_packages(arch):
    packages = defaultdict(Package)

    releasedir = os.path.join(common_constants.FTP, arch)

    for (dirpath, subdirs, files) in os.walk(releasedir):
        relpath = os.path.relpath(dirpath, releasedir)

        tars = list(filter(lambda f: re.search(r'\.tar.*$', f), files))
        tars = list(map(lambda f: os.path.join(arch, relpath, f), tars))

        if 'setup.hint' in files:
            # the package name is always the directory name
            p = os.path.basename(dirpath)

            # check for duplicate package names at different paths
            if p in packages:
                print("duplicate package name at paths %s and %s" %
                      (dirpath, packages[p].path))
                continue

            hints = hint.setup_hint_parse(os.path.join(dirpath, 'setup.hint'))
            if 'parse-errors' in hints:
                print('errors parsing hints for package %s' % p)
                continue

            packages[p].hints = hints
            packages[p].tars = tars
            packages[p].path = dirpath

        elif (len(files) > 0) and (relpath.count(os.path.sep) > 1):
            print("no setup hint in %s but files %s" % (dirpath, str(files)))

    print("%d packages" % len(packages))

    return packages

if __name__ == "__main__":
    for arch in common_constants.ARCHES:
        packages = read_packages(arch)
        for p in packages.keys():
            print(p, len(packages[p].tars))

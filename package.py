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
# utilities for working with a package database
#

from collections import defaultdict
import copy
import difflib
import logging
import os
import pprint
import re
import re
import tarfile
import textwrap
import time

import hint
import common_constants
from version import SetupVersion


class Package(object):
    def __init__(self):
        self.path = ''  # path to package, relative to release area
        self.tars = {}
        self.hints = {}


#
# read a packages from a directory hierarchy
#
def read_packages(rel_area, arch):
    packages = defaultdict(Package)

    releasedir = os.path.join(rel_area, arch)
    logging.info('reading packages from %s' % releasedir)

    for (dirpath, subdirs, files) in os.walk(releasedir):
        read_package(packages, releasedir, dirpath, files)

    logging.info("%d packages read" % len(packages))

    return packages


#
# read a single package
#
def read_package(packages, basedir, dirpath, files, strict=False):
    relpath = os.path.relpath(dirpath, basedir)
    warnings = False

    if 'setup.hint' in files:
        files.remove('setup.hint')
        # the package name is always the directory name
        p = os.path.basename(dirpath)

        # check for duplicate package names at different paths
        if p in packages:
            logging.error("duplicate package name at paths %s and %s" %
                          (dirpath, packages[p].path))
            return True

        # read setup.hints
        hints = hint.setup_hint_parse(os.path.join(dirpath, 'setup.hint'))
        if 'parse-errors' in hints:
            for l in hints['parse-errors']:
                logging.error("package '%s': %s" % (p, l))
            logging.error("errors while parsing hints for package '%s'" % p)
            return True

        # read sha512.sum
        sha512 = {}
        if 'sha512.sum' not in files:
            logging.warning("missing sha512.sum for package '%s'" % p)
            return True
        else:
            files.remove('sha512.sum')

            with open(os.path.join(dirpath, 'sha512.sum')) as fo:
                for l in fo:
                    match = re.match(r'^(\S+)\s+(?:\*|)(\S+)$', l)
                    if match:
                        sha512[match.group(2)] = match.group(1)
                    else:
                        logging.warning("bad line '%s' in sha512.sum for package '%s'" % (l, p))

        # discard obsolete md5.sum
        if 'md5.sum' in files:
            files.remove('md5.sum')

        # collect the attributes for each tar file
        tars = {}
        missing = False

        for f in list(filter(lambda f: re.search(r'\.tar.*$', f), files)):
            files.remove(f)

            # warn if tar filename doesn't follow P-V-R naming convention
            #
            # P must match the package name, V can contain anything
            # (including a '-'), R must start with a number
            if not re.match(r'^' + re.escape(p) + '-.+-\d[0-9a-zA-Z.]*(-src|)\.tar\.(xz|bz2|gz)$', f):
                logging.warning("tar file %s in package '%s' doesn't follow naming convention" % (f, p))
                warning = True

            tars[f] = {}
            tars[f]['size'] = os.path.getsize(os.path.join(dirpath, f))

            if f not in sha512:
                logging.error("no sha512.sum line for file %s in package '%s'" % (f, p))
                missing = True
            else:
                tars[f]['sha512'] = sha512[f]

        if missing:
            return True

        # warn about unexpected files, including tarfiles which don't match the
        # package name
        if files:
            logging.warning("unexpected files in %s: %s" % (p, ', '.join(files)))
            warning = True

        packages[p].hints = hints
        packages[p].tars = tars
        packages[p].path = relpath

    elif (len(files) > 0) and (relpath.count(os.path.sep) > 1):
        logging.warning("no setup.hint in %s but files: %s" % (dirpath, ', '.join(files)))

    if strict:
        return warnings
    return False


#
# utility to determine if a tar file is empty
#
def tarfile_is_empty(tf):
    # sometimes compressed empty files are used rather than a compressed empty
    # tar archive
    if os.path.getsize(tf) <= 32:
        return True

    # parsing the tar archive just to determine if it contains at least one
    # archive member is relatively expensive, so we just assume it contains
    # something if it's over a certain size threshold
    if os.path.getsize(tf) > 1024:
        return False

    # if it's really a tar file, does it contain zero files?
    with tarfile.open(tf) as a:
        if any(a) == 0:
            return True

    return False


# a sorting which forces packages which begin with '!' to be sorted first,
# packages which begin with '_" to be sorted last, and others to be sorted
# case-insensitively
def sort_key(k):
    k = k.lower()
    if k[0] == '!':
        k = chr(0) + k
    elif k[0] == '_':
        k = chr(255) + k
    return k


#
# validate the package database
#
def validate_packages(args, packages):
    error = False

    for p in sorted(packages.keys()):
        # all packages listed in requires must exist
        if 'requires' in packages[p].hints:
            for r in packages[p].hints['requires'].split():
                if r not in packages:
                    logging.error("package '%s' requires nonexistent package '%s'" % (p, r))
                    error = True

                # a package is should not appear in it's own requires
                if r == p:
                    logging.error("package '%s' requires itself" % (p))

        # if external-source is used, the package must exist
        if 'external-source' in packages[p].hints:
            e = packages[p].hints['external-source']
            if e not in packages:
                logging.error("package '%s' refers to nonexistent external-source '%s'" % (p, e))
                error = True

        packages[p].vermap = defaultdict(defaultdict)
        has_install = False
        is_empty = {}

        for t in packages[p].tars:
            # categorize each tarfile as either 'source' or 'install'
            if re.search(r'-src\.tar', t):
                category = 'source'
            else:
                category = 'install'
                has_install = True

                # check if install package is empty
                is_empty[t] = tarfile_is_empty(os.path.join(args.rel_area, args.arch, packages[p].path, t))

            # extract just the version part from tar filename
            v = re.sub(r'^' + re.escape(p) + '-', '', t)
            v = re.sub(r'(-src|)\.tar\.(xz|bz2|gz)$', '', v)

            # store tarfile corresponding to this version and category
            packages[p].vermap[v][category] = t

        # verify the versions specified for stability level exist
        levels = ['test', 'curr', 'prev']
        for l in levels:
            if l in packages[p].hints:
                # check that version exists
                v = packages[p].hints[l]
                if v not in packages[p].vermap:
                    logging.error("package '%s' stability '%s' selects non-existent version '%s'" % (p, l, v))
                    error = True

        # assign a version to each stability level
        packages[p].stability = defaultdict()

        # sort in order from highest to lowest version
        for v in sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
            level_found = False

            while True:
                # no stability levels left
                if len(levels) == 0:
                    # XXX: versions which don't correspond to any stability level
                    # should be reported, we might want to remove them at some point
                    logging.info("package '%s' has no stability levels left for version '%s'" % (p, v))
                    break

                l = levels[0]

                # if current stability level has an override
                if l in packages[p].hints:
                    # if we haven't reached that version yet
                    if v != packages[p].hints[l]:
                        break
                    else:
                        logging.info("package '%s' stability '%s' override to version '%s'" % (p, l, v))
                else:
                    # level 'test' must be assigned by override
                    if l == 'test':
                        levels.remove(l)
                        # go around again to check for override at the new level
                        continue

                level_found = True
                logging.debug("package '%s' stability '%s' assigned version '%s'" % (p, l, v))
                break

            if not level_found:
                continue

            # assign version to level
            packages[p].stability[l] = v
            # and remove from list of unallocated levels
            levels.remove(l)

        # lastly, fill in any levels which we skipped over because a higher
        # stability level was overriden to a lower version
        for l in levels:
            if l in packages[p].hints:
                packages[p].stability[l] = packages[p].hints[l]

        # verify that versions have files
        for v in sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
            required_categories = []

            # a source tarfile must exist for every version, unless
            # - the install tarfile is empty, or
            # - this package is external-source
            if 'external-source' not in packages[p].hints:
                if 'install' in packages[p].vermap[v]:
                    if not is_empty[packages[p].vermap[v]['install']]:
                        required_categories.append('source')

            # XXX: actually we should verify that a source tarfile must exist
            # for every install tarfile version, but it may be either in this
            # package or in the external-source package...

            # similarly, we should verify that each version has an install
            # tarfile, unless this is a source-only package.  Unfortunately, the
            # current data model doesn't clearly identify those.  For the
            # moment, if we have seen at least one install tarfile, assume we
            # aren't a source-only package.
            if has_install:
                required_categories.append('install')

            for c in required_categories:
                if c not in packages[p].vermap[v]:
                    # logging.error("package '%s' version '%s' is missing %s tarfile" % (p, v, c))
                    # error = True
                    pass

        # for historical reasons, add cygwin to requires if not already present,
        # the package is not source-only, not empty, not only contains symlinks,
        # and not on the list to avoid doing this for
        # (this approximates what 'autodep' did)
        if has_install and (not all(is_empty.values())) and (p not in ['base-cygwin', 'gcc4-core', 'gcc4-g++']):
            requires = packages[p].hints.get('requires', '')

            if not re.search(r'\bcygwin\b', requires):
                if len(requires) > 0:
                    requires = requires + ' '
                packages[p].hints['requires'] = requires + 'cygwin'

        # if the package has no install tarfiles (i.e. is source only), mark it
        # as 'skip' (which really means 'source-only' at the moment)
        if not has_install and 'skip' not in packages[p].hints:
            packages[p].hints['skip'] = ''

    return not error


#
# write setup.ini
#
def write_setup_ini(args, packages):

    with open(args.inifile, 'w') as f:
        # write setup.ini header
        print(textwrap.dedent('''\
        # This file is automatically generated.  If you edit it, your
        # edits will be discarded next time the file is generated.
        # See http://cygwin.com/setup.html for details.
        #'''), file=f)

        if args.release:
            print("release: %s" % args.release, file=f)
        print("arch: %s" % args.arch, file=f)
        print("setup-timestamp: %d" % time.time(), file=f)
        if args.setup_version:
            print("setup-version: %s" % args.setup_version, file=f)

        # for each package
        for p in sorted(packages.keys(), key=sort_key):
            # do nothing if 'skip'
            if 'skip' in packages[p].hints:
                continue

            # write package data
            print("\n@ %s" % p, file=f)

            # for historical reasons, we adjust sdesc slightly:
            #
            # - strip anything up to and including first ':'
            # - capitalize first letter
            # whilst preserving any leading quote
            #
            # these are both bad ideas, due to sdesc's which start with a
            # lower-case command name, or contain perl or ruby module names like
            # 'Net::HTTP'
            sdesc = packages[p].hints['sdesc']
            sdesc = re.sub('^("?)(.*?)("?)$', r'\2', sdesc)
            if ':' in sdesc:
                sdesc = re.sub(r'^[^:]+:\s*', '', sdesc)
            sdesc = '"' + upper_first_character(sdesc) + '"'
            print("sdesc: %s" % sdesc, file=f)

            if 'ldesc' in packages[p].hints:
                print("ldesc: %s" % packages[p].hints['ldesc'], file=f)

            # for historical reasons, category names must start with a capital
            # letter
            category = ' '.join(map(upper_first_character, packages[p].hints['category'].split()))
            print("category: %s" % category, file=f)

            if 'requires' in packages[p].hints:
                # for historical reasons, empty requires are suppressed
                requires = packages[p].hints['requires']
                if requires:
                    print("requires: %s" % requires, file=f)

            # write tarfile lines for each stability level
            for level in ['curr', 'prev', 'test']:
                if level in packages[p].stability:
                    version = packages[p].stability[level]
                    if level != 'curr':
                        print("[%s]" % level, file=f)
                    print("version: %s" % version, file=f)

                    if 'install' in packages[p].vermap[version]:
                        t = packages[p].vermap[version]['install']
                        tar_line('install', args.arch, packages[p], t, f)

                    # look for corresponding source in this package first
                    if 'source' in packages[p].vermap[version]:
                        t = packages[p].vermap[version]['source']
                        tar_line('source', args.arch, packages[p], t, f)
                    # if that doesn't exist, follow external-source
                    elif 'external-source' in packages[p].hints:
                        s = packages[p].hints['external-source']
                        t = packages[s].vermap[version]['source']
                        tar_line('source', args.arch, packages[s], t, f)

            if 'message' in packages[p].hints:
                print("message: %s" % packages[p].hints['message'], file=f)


# helper function to output details for a particular tar file
def tar_line(category, arch, p, t, f):
    fn = os.path.join(arch, p.path, t)
    sha512 = p.tars[t]['sha512']
    size = p.tars[t]['size']
    print("%s: %s %d %s" % (category, fn, size, sha512), file=f)


# helper function to change the first character of a string to upper case,
# without altering the rest
def upper_first_character(s):
    return s[:1].upper() + s[1:]


#
# merge two sets of packages
#
# for each package which exist in both a and b:
# - they must exist at the same relative path, or the package from a is used
# - we combine the list of tarfiles, duplicates are not expected
# - we use the hints from b, and warn if they are different to the hints for a
#
def merge(a, b):
    # start with a copy of a
    c = copy.deepcopy(a)

    for p in b:
        # if the package is in b but not in a, add it to the copy
        if p not in a:
            c[p] = b[p]
        # else, if the package is both in a and b, we have to do a merge
        else:
            # package must exist at same relative path
            if a[p].path != b[p].path:
                logging.error("package name %s at paths %s and %s" % (p, a[p].path, b[p].path))
            else:
                for t in b[p].tars:
                    if t in c[p].tars:
                        logging.error("package name %s duplicate tarfile %s" % (p, t))
                    else:
                        c[p].tars[t] = b[p].tars[t]

                # use hints from b, but warn that they have changed
                if a[p].hints != b[p].hints:
                    c[p].hints = b[p].hints

                    diff = '\n'.join(difflib.ndiff(
                        pprint.pformat(a[p].hints).splitlines(),
                        pprint.pformat(b[p].hints).splitlines()))

                    logging.warning("package name %s hints changed\n%s\n" % (p, diff))

    return c


#
#
#
if __name__ == "__main__":
    for arch in common_constants.ARCHES:
        packages = read_packages(common_constants.FTP, arch)
        print("arch %s has %d packages" % (arch, len(packages)))

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
import hashlib
import logging
import os
import pprint
import re
import tarfile
import textwrap
import time

from .version import SetupVersion
from . import common_constants
from . import hint
from . import maintainers
from . import past_mistakes


# information we keep about a package
class Package(object):
    def __init__(self):
        self.path = ''  # path to package, relative to release area
        self.tars = {}
        self.hints = {}

    def __repr__(self):
        return "Package('%s', %s, %s)" % (self.path, pprint.pformat(self.tars),
                                          pprint.pformat(self.hints))


# information we keep about a tar file
class Tar(object):
    def __init__(self):
        self.sha512 = ''
        self.size = 0
        self.is_empty = False
        self.is_used = False

    def __repr__(self):
        return "Tar('%s', %d, %s)" % (self.sha512, self.size, self.is_empty)


#
# read a packages from a directory hierarchy
#
def read_packages(rel_area, arch):
    packages = defaultdict(Package)

    # both noarch/ and <arch>/ directories are considered
    for root in ['noarch', arch]:
        releasedir = os.path.join(rel_area, root)
        logging.debug('reading packages from %s' % releasedir)

        for (dirpath, subdirs, files) in os.walk(releasedir):
            read_package(packages, rel_area, dirpath, files)

        logging.debug("%d packages read" % len(packages))

    return packages


# helper function to compute sha512 for a particular file
# (block_size should be some multiple of sha512 block size which can be efficiently read)
def sha512_file(fn, block_size=256*128):
    sha512 = hashlib.sha512()

    with open(fn, 'rb') as f:
        for chunk in iter(lambda: f.read(block_size), b''):
            sha512.update(chunk)

    return sha512.hexdigest()


#
# read a single package
#
def read_package(packages, basedir, dirpath, files, strict=False):
    strict_lvl = logging.ERROR if strict else logging.WARNING
    relpath = os.path.relpath(dirpath, basedir)
    warnings = False

    if 'setup.hint' in files:
        files.remove('setup.hint')
        # the package name is always the directory name
        p = os.path.basename(dirpath)

        if not re.match(r'^[\w\-._+]*$', p):
            logging.error("package '%s' name contains illegal characters" % p)
            return True

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
        if 'parse-warnings' in hints:
            for l in hints['parse-warnings']:
                logging.info("package '%s': %s" % (p, l))

        # read sha512.sum
        sha512 = {}
        if 'sha512.sum' not in files:
            logging.debug("no sha512.sum for package '%s'" % p)
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

        for f in list(filter(lambda f: re.match(r'^' + re.escape(p) + r'.*\.tar.*$', f), files)):
            files.remove(f)

            # warn if tar filename doesn't follow P-V-R naming convention
            #
            # P must match the package name, V can contain anything, R must
            # start with a number
            match = re.match(r'^' + re.escape(p) + '-(.+)-(\d[0-9a-zA-Z.]*)(-src|)\.tar\.(bz2|gz|lzma|xz)$', f)
            if not match:
                logging.log(strict_lvl, "tar file '%s' in package '%s' doesn't follow naming convention" % (f, p))
                warnings = True
            else:
                # historically, V can contain a '-' (since we can use the fact
                # we already know P to split unambiguously), but this is a bad
                # idea.
                if '-' in match.group(1):
                    lvl = logging.WARNING if p not in past_mistakes.hyphen_in_version else logging.INFO
                    logging.log(lvl, "tar file '%s' in package '%s' contains '-' in version" % (f, p))

                if not match.group(1)[0].isdigit():
                    logging.warning("tar file '%s' in package '%s' has a version which doesn't start with a digit" % (f, p))

            tars[f] = Tar()
            tars[f].size = os.path.getsize(os.path.join(dirpath, f))
            tars[f].is_empty = tarfile_is_empty(os.path.join(dirpath, f))

            if f in sha512:
                tars[f].sha512 = sha512[f]
            else:
                tars[f].sha512 = sha512_file(os.path.join(dirpath, f))
                logging.debug("no sha512.sum line for file %s in package '%s', computed sha512 hash is %s" % (f, p, tars[f].sha512))

        # ignore dotfiles
        for f in files:
            if f.startswith('.'):
                files.remove(f)

        # warn about unexpected files, including tarfiles which don't match the
        # package name
        if files:
            logging.log(strict_lvl, "unexpected files in %s: %s" % (p, ', '.join(files)))
            warnings = True

        packages[p].hints = hints
        packages[p].tars = tars
        packages[p].path = relpath

        #
        # now we have read the package, fix some common defects in the hints
        #

        # don't allow a redundant 'package:' or 'package - ' at start of sdesc
        #
        # match case-insensitively, and use a base package name (trim off any
        # leading 'lib' from package name, remove any soversion or 'devel'
        # suffix)
        #
        if 'sdesc' in hints:
            colon = re.match(r'^"(.*?)(\s*:|\s+-)', hints['sdesc'])
            if colon:
                package_basename = re.sub(r'^lib(.*?)(|-devel|\d*)$', r'\1', p)
                if package_basename.upper().startswith(colon.group(1).upper()):
                    logging.log(strict_lvl, "package '%s' sdesc starts with '%s'; this is redundant as the UI will show both the package name and sdesc" % (p, ''.join(colon.group(1, 2))))
                    warnings = True

    elif (len(files) > 0) and (relpath.count(os.path.sep) > 1):
        logging.warning("no setup.hint in %s but has files: %s" % (dirpath, ', '.join(files)))

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
        logging.debug("validating package '%s'" % (p))

        if 'required-package' not in getattr(args, 'okmissing', []):
            # all packages listed in requires must exist
            if 'requires' in packages[p].hints:
                for r in packages[p].hints['requires'].split():
                    if r not in packages:
                        logging.error("package '%s' requires nonexistent package '%s'" % (p, r))
                        error = True

                        # a package is should not appear in it's own requires
                        if r == p:
                            lvl = logging.WARNING if p not in past_mistakes.self_requires else logging.INFO
                            logging.log(lvl, "package '%s' requires itself" % (p))

        # if external-source is used, the package must exist
        if 'external-source' in packages[p].hints:
            e = packages[p].hints['external-source']
            if e not in packages:
                logging.error("package '%s' refers to nonexistent external-source '%s'" % (p, e))
                error = True

        packages[p].vermap = defaultdict(defaultdict)
        is_empty = {}
        has_install = False

        for t in packages[p].tars:
            # categorize each tarfile as either 'source' or 'install'
            if re.search(r'-src\.tar', t):
                category = 'source'
            else:
                category = 'install'
                has_install = True
                is_empty[t] = packages[p].tars[t].is_empty

            # extract just the version part from tar filename
            v = re.sub(r'^' + re.escape(p) + '-', '', t)
            v = re.sub(r'(-src|)\.tar\.(bz2|gz|lzma|xz)$', '', v)

            # for each version, a package can contain at most one source tar
            # file and at most one install tar file.  warn if we have too many
            # (for e.g. both a .xz and .bz2 install tar file)
            if category in packages[p].vermap[v]:
                logging.error("package '%s' has more than one %s tar file for version '%s'" % (p, category, v))
                error = True

            # store tarfile corresponding to this version and category
            packages[p].vermap[v][category] = t

        # if the package has no install tarfiles (i.e. is source only), make
        # sure it is marked as 'skip' (which really means 'source-only' at the
        # moment)
        #
        # (this needs to take place after uploads have been merged into the
        # package set, so that an upload containing just a replacement
        # setup.hint is not considered a source-only package)
        #
        # XXX: the check should probably be for any non-empty install files, but
        # that differs from what upset does
        if not has_install and 'skip' not in packages[p].hints:
            packages[p].hints['skip'] = ''
            logging.info("package '%s' appears to be source-only as it has no install tarfiles, adding 'skip:' hint" % (p))

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
                    logging.log(5, "package '%s' has no stability levels left for version '%s'" % (p, v))
                    break

                l = levels[0]

                # if current stability level has an override
                if l in packages[p].hints:
                    # if we haven't reached that version yet
                    if v != packages[p].hints[l]:
                        break
                    else:
                        logging.debug("package '%s' stability '%s' overridden to version '%s'" % (p, l, v))
                else:
                    # level 'test' must be assigned by override
                    if l == 'test':
                        levels.remove(l)
                        # go around again to check for override at the new level
                        continue

                level_found = True
                logging.log(5, "package '%s' stability '%s' assigned version '%s'" % (p, l, v))
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

        # If, for every stability level, the install tarball is empty and there
        # is no source tarball, we should probably be marked obsolete
        if 'skip' not in packages[p].hints:
            if '_obsolete' not in packages[p].hints['category']:
                has_something = False

                for l in ['test', 'curr', 'prev']:
                    if l in packages[p].stability:
                        v = packages[p].stability[l]
                        if 'source' in packages[p].vermap[v]:
                            has_something = True
                        elif 'install' in packages[p].vermap[v]:
                            if not packages[p].tars[packages[p].vermap[v]['install']].is_empty:
                                has_something = True

                if not has_something:
                    logging.warning("package '%s' has empty install tar file and no source for all levels, but it's not in the _obsolete category" % (p))

    # make another pass to verify a source tarfile exists for every install
    # tarfile version
    for p in sorted(packages.keys()):
        for v in sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
            if 'install' not in packages[p].vermap[v]:
                continue

            # unless the install tarfile is empty
            if packages[p].tars[packages[p].vermap[v]['install']].is_empty:
                continue

            # source tarfile may be either in this package or in the
            # external-source package
            #
            # mark the source tarfile as being used by an install tarfile
            if 'source' in packages[p].vermap[v]:
                packages[p].tars[packages[p].vermap[v]['source']].is_used = True
                continue

            if 'external-source' in packages[p].hints:
                es_p = packages[p].hints['external-source']
                if es_p in packages:
                    if 'source' in packages[es_p].vermap[v]:
                        packages[es_p].tars[packages[es_p].vermap[v]['source']].is_used = True
                        continue

            # unless this package is marked as 'self-source'
            if p in past_mistakes.self_source:
                continue

            logging.error("package '%s' version '%s' is missing source" % (p, v))
            error = True

    # make another pass to verify that each non-empty source tarfile version has
    # at least one corresponding non-empty install tarfile, in some package.
    for p in sorted(packages.keys()):
        for v in sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
            if 'source' not in packages[p].vermap[v]:
                continue

            if packages[p].tars[packages[p].vermap[v]['source']].is_empty:
                continue

            if not packages[p].tars[packages[p].vermap[v]['source']].is_used:
                logging.error("package '%s' version '%s' source has no non-empty install tarfiles" % (p, v))
                error = True

    # validate that all packages are in the package maintainers list
    validate_package_maintainers(args, packages)

    return not error


#
def validate_package_maintainers(args, packages):
    if not args.pkglist:
        return

    # read maintainer list
    mlist = {}
    mlist = maintainers.Maintainer.add_packages(mlist, args.pkglist)

    # make the list of all packages
    all_packages = maintainers.Maintainer.all_packages(mlist)

    # validate that all packages are in the package list
    for p in sorted(packages):
        # ignore skip packages
        if 'skip' in packages[p].hints:
            continue
        # ignore obsolete packages
        if '_obsolete' in packages[p].hints['category']:
            continue
        if not is_in_package_list(packages[p].path, all_packages):
            logging.error("package '%s' is not in the package list" % (p))


#
# write setup.ini
#
def write_setup_ini(args, packages, arch):

    logging.debug('writing %s' % (args.inifile))

    with open(args.inifile, 'w') as f:
        os.fchmod(f.fileno(), 0o644)

        # write setup.ini header
        print(textwrap.dedent('''\
        # This file is automatically generated.  If you edit it, your
        # edits will be discarded next time the file is generated.
        # See http://cygwin.com/setup.html for details.
        #'''), file=f)

        if args.release:
            print("release: %s" % args.release, file=f)
        print("arch: %s" % arch, file=f)
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

            print("sdesc: %s" % packages[p].hints['sdesc'], file=f)

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
                        tar_line('install', packages[p], t, f)

                    # look for corresponding source in this package first
                    if 'source' in packages[p].vermap[version]:
                        t = packages[p].vermap[version]['source']
                        tar_line('source', packages[p], t, f)
                    # if that doesn't exist, follow external-source
                    elif 'external-source' in packages[p].hints:
                        s = packages[p].hints['external-source']
                        if 'source' in packages[s].vermap[version]:
                            t = packages[s].vermap[version]['source']
                            tar_line('source', packages[s], t, f)
                        else:
                            logging.warning("package '%s' version '%s' has no source in external-source '%s'" % (p, version, s))

            if 'message' in packages[p].hints:
                print("message: %s" % packages[p].hints['message'], file=f)


# helper function to output details for a particular tar file
def tar_line(category, p, t, f):
    fn = os.path.join(p.path, t)
    sha512 = p.tars[t].sha512
    size = p.tars[t].size
    print("%s: %s %d %s" % (category, fn, size, sha512), file=f)


# helper function to change the first character of a string to upper case,
# without altering the rest
def upper_first_character(s):
    return s[:1].upper() + s[1:]


#
# merge sets of packages
#
# for each package which exist in both a and b:
# - they must exist at the same relative path
# - we combine the list of tarfiles, duplicates are not permitted
# - we use the hints from b, and warn if they are different to the hints for a
#
def merge(a, *l):
    # start with a copy of a
    c = copy.deepcopy(a)

    for b in l:
        for p in b:
            # if the package is in b but not in a, add it to the copy
            if p not in a:
                c[p] = b[p]
            # else, if the package is both in a and b, we have to do a merge
            else:
                # package must exist at same relative path
                if a[p].path != b[p].path:
                    logging.error("package '%s' is at paths %s and %s" % (p, a[p].path, b[p].path))
                    return None
                else:
                    for t in b[p].tars:
                        if t in c[p].tars:
                            logging.error("package '%s' has duplicate tarfile %s" % (p, t))
                            return None
                        else:
                            c[p].tars[t] = b[p].tars[t]

                    # use hints from b, but warn if they have changed
                    if a[p].hints != b[p].hints:
                        c[p].hints = b[p].hints

                        diff = '\n'.join(difflib.ndiff(
                            pprint.pformat(a[p].hints).splitlines(),
                            pprint.pformat(b[p].hints).splitlines()))

                        logging.warning("package '%s' hints changed\n%s" % (p, diff))

    return c


#
# delete a file from a package set
#

def delete(packages, path, fn):
    for p in packages:
        if packages[p].path == path:
            for t in packages[p].tars:
                if t == fn:
                    del packages[p].tars[t]
                    break


#
# verify that the package ppath is in the list of packages plist
#
# (This means that a maintainer can upload a package with any name, provided the
# path contains one allowed for that maintainer)
#
# This avoids the need to have to explicitly list foo, foo_autorebase,
# foo-devel, foo-doc, foo-debuginfo, libfoo0, girepository-foo, etc. instead of
# just foo in the package list
#
# But means only the rule that a package can't exist in multiple paths prevents
# arbitrary package upload.
#

def package_list_re(plist):
    if getattr(package_list_re, "_plist", []) != plist:
        pattern = '|'.join(map(lambda p: r'/' + re.escape(p) + r'(?:/|$)', plist))
        package_list_re._regex = re.compile(pattern, re.IGNORECASE)
        package_list_re._plist = plist

    return package_list_re._regex


def is_in_package_list(ppath, plist):
    if package_list_re(plist).search(ppath):
        return True

    return False


#
#
#
if __name__ == "__main__":
    for arch in common_constants.ARCHES:
        packages = read_packages(common_constants.FTP, arch)
        print("arch %s has %d packages" % (arch, len(packages)))

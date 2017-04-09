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
        self.is_used_by = set()
        self.version_hints = {}
        self.override_hints = {}
        self.skip = False

    def __repr__(self):
        return "Package('%s', %s, %s, %s, %s)" % (
            self.path,
            pprint.pformat(self.tars),
            pprint.pformat(self.version_hints),
            pprint.pformat(self.override_hints),
            self.skip)


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

        for (dirpath, subdirs, files) in os.walk(releasedir, followlinks=True):
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


# helper function to read hints
def read_hints(p, fn, kind):
    hints = hint.hint_file_parse(fn, kind)

    if 'parse-errors' in hints:
        for l in hints['parse-errors']:
            logging.error("package '%s': %s" % (p, l))
        logging.error("errors while parsing hints for package '%s'" % p)
        return None

    if 'parse-warnings' in hints:
        for l in hints['parse-warnings']:
            logging.info("package '%s': %s" % (p, l))

    return hints


# helper function to clean up hints
def clean_hints(p, hints, strict_lvl, warnings):
    #
    # fix some common defects in the hints
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

    return warnings


#
# read a single package
#
def read_package(packages, basedir, dirpath, files, strict=False, remove=[], upload=False):
    strict_lvl = logging.ERROR if strict else logging.WARNING
    relpath = os.path.relpath(dirpath, basedir)
    warnings = False

    if any([f.endswith('.hint') for f in files]):
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

        # read setup.hint
        legacy = 'setup.hint' in files
        legacy_used = False
        if legacy:
            hints = read_hints(p, os.path.join(dirpath, 'setup.hint'), hint.setup)
            if not hints:
                return True
            warnings = clean_hints(p, hints, strict_lvl, warnings)
            files.remove('setup.hint')
        else:
            hints = {}

        # determine version overrides
        note_absent = ('override.hint' in remove) or ('override.hint' in files) or legacy

        if 'override.hint' in files:
            # read override.hint
            override_hints = read_hints(p, os.path.join(dirpath, 'override.hint'), hint.override)
            files.remove('override.hint')
        else:
            override_hints = {}

            # if we didn't have a version override hint, extract any version
            # override from legacy hints
            for level in ['test', 'curr', 'prev']:
                if level in hints:
                    override_hints[level] = hints[level]

        # if override.hint exists or is being removed, explicitly note absent
        # stability level hints
        if note_absent:
            for level in ['test', 'curr', 'prev']:
                if level not in override_hints:
                    override_hints[level] = None

        # after we have migrated them to override hints, remove stability
        # level hints from legacy hints
        for level in ['test', 'curr', 'prev']:
            if level in hints:
                del hints[level]

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

        # build a list of version-releases (since replacement pvr.hint files are
        # allowed to be uploaded, we must consider both .tar and .hint files for
        # that), and collect the attributes for each tar file
        tars = {}
        vr_list = set()

        for f in list(files):
            match = re.match(r'^' + re.escape(p) + r'.*\.(tar\.(bz2|gz|lzma|xz)|hint)$', f)
            if not match:
                continue

            if not f.endswith('.hint'):
                files.remove(f)

            # warn if filename doesn't follow P-V-R naming convention
            #
            # P must match the package name, V can contain anything, R must
            # start with a number
            match = re.match(r'^' + re.escape(p) + '-(.+)-(\d[0-9a-zA-Z.]*)(-src|)\.' + match.group(1) + '$', f)
            if not match:
                logging.log(strict_lvl, "file '%s' in package '%s' doesn't follow naming convention" % (f, p))
                warnings = True
            else:
                v = match.group(1)
                r = match.group(2)

                # historically, V can contain a '-' (since we can use the fact
                # we already know P to split unambiguously), but this is a bad
                # idea.
                if '-' in v:
                    lvl = logging.WARNING if p not in past_mistakes.hyphen_in_version else logging.INFO
                    logging.log(lvl, "file '%s' in package '%s' contains '-' in version" % (f, p))

                if not v[0].isdigit():
                    logging.warning("file '%s' in package '%s' has a version which doesn't start with a digit" % (f, p))

                # if not there already, add to version-release list
                vr_list.add('%s-%s' % (v, r))

            if not f.endswith('.hint'):
                # collect the attributes for each tar file
                tars[f] = Tar()
                tars[f].size = os.path.getsize(os.path.join(dirpath, f))
                tars[f].is_empty = tarfile_is_empty(os.path.join(dirpath, f))
                tars[f].mtime = os.path.getmtime(os.path.join(dirpath, f))

                if f in sha512:
                    tars[f].sha512 = sha512[f]
                else:
                    tars[f].sha512 = sha512_file(os.path.join(dirpath, f))
                    logging.debug("no sha512.sum line for file %s in package '%s', computed sha512 hash is %s" % (f, p, tars[f].sha512))

        # determine hints for each version we've encountered
        version_hints = {}
        hint_files = {}
        for vr in vr_list:
            hint_fn = '%s-%s.hint' % (p, vr)
            if hint_fn in files:
                # is there a PVR.hint file?
                pvr_hint = read_hints(p, os.path.join(dirpath,  hint_fn), hint.pvr)
                if not pvr_hint:
                    return True
                warnings = clean_hints(p, pvr_hint, strict_lvl, warnings)
                files.remove(hint_fn)
                hint_files[vr] = hint_fn
            elif legacy:
                # otherwise, use setup.hint
                pvr_hint = hints
                legacy_used = True
            else:
                # it's an error to not have either a setup.hint or a pvr.hint
                logging.error("package %s has packages for version %s, but no %s or setup.hint" % (p, vr, hint_fn))
                return True

            version_hints[vr] = pvr_hint

        # ignore dotfiles
        for f in files:
            if f.startswith('.'):
                files.remove(f)

        # warn about unexpected files, including tarfiles which don't match the
        # package name
        if files:
            logging.log(strict_lvl, "unexpected files in %s: %s" % (p, ', '.join(files)))
            warnings = True

        if not upload and legacy and not legacy_used:
            logging.warning("package '%s' has a setup.hint which no version uses, removing it" % (p))
            os.unlink(os.path.join(dirpath, 'setup.hint'))

        packages[p].version_hints = version_hints
        packages[p].override_hints = override_hints
        packages[p].legacy_hints = hints
        packages[p].tars = tars
        packages[p].hint_files = hint_files
        packages[p].path = relpath
        packages[p].skip = any(['skip' in version_hints[vr] for vr in vr_list])

    elif (len(files) > 0) and (relpath.count(os.path.sep) > 1):
        logging.warning("no .hint files in %s but has files: %s" % (dirpath, ', '.join(files)))

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
    try:
        with tarfile.open(tf) as a:
            if any(a) == 0:
                return True
    except Exception as e:
        logging.error("exception %s while reading %s" % (type(e).__name__, tf))
        logging.debug('', exc_info=True)

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
        logging.log(5, "validating package '%s'" % (p))
        has_requires = False

        for (v, hints) in packages[p].version_hints.items():
            if 'requires' in hints:
                for r in hints['requires'].split():
                    has_requires = True

                    # a package should not appear in it's own requires
                    if r == p:
                        lvl = logging.WARNING if p not in past_mistakes.self_requires else logging.DEBUG
                        logging.log(lvl, "package '%s' version '%s' requires itself" % (p, v))

                    # all packages listed in requires must exist (unless
                    # okmissing says that's ok)
                    if r not in packages:
                        if 'required-package' not in getattr(args, 'okmissing', []):
                            logging.error("package '%s' version '%s' requires nonexistent package '%s'" % (p, v, r))
                            error = True
                        continue

                    # requiring a source-only package makes no sense
                    if packages[r].skip:
                        logging.error("package '%s' version '%s' requires source-only package '%s'" % (p, v, r))
                        error = True

            # if external-source is used, the package must exist
            if 'external-source' in hints:
                e = hints['external-source']
                if e not in packages:
                    logging.error("package '%s' version '%s' refers to nonexistent external-source '%s'" % (p, v, e))
                    error = True

        packages[p].vermap = defaultdict(defaultdict)
        is_empty = {}
        has_install = False
        has_nonempty_install = False

        for t in packages[p].tars:
            # categorize each tarfile as either 'source' or 'install'
            if re.search(r'-src\.tar', t):
                category = 'source'
            else:
                category = 'install'
                has_install = True
                is_empty[t] = packages[p].tars[t].is_empty
                if not is_empty[t]:
                    has_nonempty_install = True

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

        obsolete = any(['_obsolete' in packages[p].version_hints[vr].get('category', '') for vr in packages[p].version_hints])

        # if the package has no install tarfiles (i.e. is source only), make
        # sure it is marked as 'skip' (which really means 'source-only' at the
        # moment)
        #
        # if the package has no non-empty install tarfiles, and no dependencies
        # installing it will do nothing (and making it appear in the package
        # list is just confusing), so if it's not obsolete, mark it as 'skip'
        #
        # (this needs to take place after uploads have been merged into the
        # package set, so that an upload containing just a replacement
        # setup.hint is not considered a source-only package)
        #
        if not packages[p].skip:
            if not has_install:
                packages[p].skip = True
                logging.info("package '%s' appears to be source-only as it has no install tarfiles, marking as 'skip'" % (p))

            elif not has_nonempty_install and not has_requires and not obsolete:
                packages[p].skip = True
                logging.info("package '%s' appears to be source-only as it has no non-empty install tarfiles and no dependencies, marking as 'skip'" % (p))

        # verify the versions specified for stability level exist
        levels = ['test', 'curr', 'prev']
        for l in levels:
            if l in packages[p].override_hints:
                # check that if a version was specified, it exists
                v = packages[p].override_hints[l]

                if v is None:
                    continue

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
                if (l in packages[p].override_hints) and (packages[p].override_hints[l] is not None):
                    # if we haven't reached that version yet
                    if v != packages[p].override_hints[l]:
                        break
                    else:
                        logging.debug("package '%s' stability '%s' overridden to version '%s'" % (p, l, v))
                # if package is explicitly marked as having that stability level
                # (only used for test, currently)
                elif (l == 'test') and ('test' in packages[p].version_hints[v]):
                    logging.debug("package '%s' version '%s' marked as stability '%s'" % (p, v, l))
                else:
                    # level 'test' must be assigned by override
                    if l == 'test':
                        levels.remove(l)
                        # go around again to check for override at the new level
                        continue
                    else:
                        # if version is explicitly marked test, it can't be
                        # assigned to any other stability level
                        if 'test' in packages[p].version_hints[v]:
                            logging.debug("package '%s' version '%s' can't be used for stability '%s' as it's marked test" % (p, v, l))
                            break

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
            if l in packages[p].override_hints:
                if packages[p].override_hints[l] is not None:
                    packages[p].stability[l] = packages[p].override_hints[l]

        # the package must have some versions
        if not packages[p].stability:
            logging.error("no versions at any stability level for package '%s'" % (p))
            error = True
        # it's also probably a really good idea if a curr version exists
        elif 'curr' not in packages[p].stability and 'curr' not in getattr(args, 'okmissing', []):
            logging.warning("package '%s' doesn't have a curr version" % (p))

        # identify a 'best' version to take certain information from: this is
        # the curr version, if we have one, otherwise, the highest version.
        if 'curr' in packages[p].stability:
            packages[p].best_version = packages[p].stability['curr']
        elif len(packages[p].vermap):
            packages[p].best_version = sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True)[0]
        else:
            logging.error("package '%s' doesn't have any versions" % (p))
            packages[p].best_version = None
            error = True

        # If the install tarball is empty and there is no source tarball, we
        # should probably be marked obsolete
        # (XXX: should consider external-source: ?)
        if not packages[p].skip:
            for vr in packages[p].version_hints:
                if '_obsolete' not in packages[p].version_hints[vr].get('category', ''):
                    if 'source' not in packages[p].vermap[vr]:
                        if 'install' in packages[p].vermap[vr]:
                            if packages[p].tars[packages[p].vermap[vr]['install']].is_empty:
                                lvl = logging.WARNING if p not in past_mistakes.empty_but_not_obsolete else logging.DEBUG
                                logging.log(lvl, "package '%s' version '%s' has empty install tar file and no source, but it's not in the _obsolete category" % (p, vr))

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
                packages[p].is_used_by.add(p)
                continue

            if 'external-source' in packages[p].version_hints[v]:
                es_p = packages[p].version_hints[v]['external-source']
                if es_p in packages:
                    if 'source' in packages[es_p].vermap[v]:
                        packages[es_p].tars[packages[es_p].vermap[v]['source']].is_used = True
                        packages[es_p].is_used_by.add(p)
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

    # do all the packages which use this source package have the same
    # current version?
    for source_p in sorted(packages.keys()):
        versions = defaultdict(list)

        for install_p in packages[source_p].is_used_by:
            # ignore obsolete packages
            if any(['_obsolete' in packages[install_p].version_hints[vr]['category'] for vr in packages[install_p].version_hints]):
                continue

            # ignore runtime library packages, as we may keep old versions of
            # those
            if re.match(r'^lib.*\d', install_p):
                continue

            # ignore specific packages
            if install_p in past_mistakes.nonunique_versions:
                continue

            versions[packages[install_p].best_version].append(install_p)

        if len(versions) > 1:
            out = []
            most_common = True

            for v in sorted(versions, key=lambda v: len(versions[v]), reverse=True):
                # try to keep the output compact by not listing all the packages
                # the most common current version has, unless it's only one.
                if most_common and len(versions[v]) != 1:
                    out.append("%s (%s others)" % (v, len(versions[v])))
                else:
                    out.append("%s (%s)" % (v, ','.join(versions[v])))
                most_common = False

            error = True
            logging.error("install packages from source package '%s' have non-unique current versions %s" % (source_p, ', '.join(reversed(out))))

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
        if packages[p].skip:
            continue
        # ignore obsolete packages
        if any(['_obsolete' in packages[p].version_hints[vr]['category'] for vr in packages[p].version_hints]):
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

        tz = time.time()
        # write setup.ini header
        print(textwrap.dedent('''\
        # This file was automatically generated at %s.
        #
        # If you edit it, your edits will be discarded next time the file is
        # generated.  See http://cygwin.com/setup.html for details.''')
              % (time.strftime("%F %T %Z", time.localtime(tz))),
              file=f)

        if args.release:
            print("release: %s" % args.release, file=f)
        print("arch: %s" % arch, file=f)
        print("setup-timestamp: %d" % tz, file=f)
        if args.setup_version:
            print("setup-version: %s" % args.setup_version, file=f)

        # for each package
        for p in sorted(packages.keys(), key=sort_key):
            # do nothing if 'skip'
            if packages[p].skip:
                continue

            # write package data
            print("\n@ %s" % p, file=f)

            bv = packages[p].best_version
            print("sdesc: %s" % packages[p].version_hints[bv]['sdesc'], file=f)

            if 'ldesc' in packages[p].version_hints[bv]:
                print("ldesc: %s" % packages[p].version_hints[bv]['ldesc'], file=f)

            # for historical reasons, category names must start with a capital
            # letter
            category = ' '.join(map(upper_first_character, packages[p].version_hints[bv]['category'].split()))
            print("category: %s" % category, file=f)

            # compute the union of requires for all versions
            requires = set()
            for hints in packages[p].version_hints.values():
                if 'requires' in hints:
                    requires = set.union(requires, hints['requires'].split())
            # for historical reasons, empty requires are suppressed
            if requires:
                print("requires: %s" % ' '.join(sorted(requires)), file=f)

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
                    elif 'external-source' in packages[p].version_hints[version]:
                        s = packages[p].version_hints[version]['external-source']
                        if 'source' in packages[s].vermap[version]:
                            t = packages[s].vermap[version]['source']
                            tar_line('source', packages[s], t, f)
                        else:
                            logging.warning("package '%s' version '%s' has no source in external-source '%s'" % (p, version, s))

            if 'message' in packages[p].version_hints[bv]:
                print("message: %s" % packages[p].version_hints[bv]['message'], file=f)


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
# (XXX: this implementation possibly assumes that a package is at most in a and
# one of b, which is currently true, but it could be written with more
# generality)
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

                    # hints from b override hints from a, but warn if they have
                    # changed
                    c[p].version_hints = a[p].version_hints
                    for vr in b[p].version_hints:
                        c[p].version_hints[vr] = b[p].version_hints[vr]
                        if vr in a[p].version_hints:
                            if a[p].version_hints[vr] != b[p].version_hints[vr]:
                                diff = '\n'.join(difflib.ndiff(
                                    pprint.pformat(a[p].version_hints[vr]).splitlines(),
                                    pprint.pformat(b[p].version_hints[vr]).splitlines()))

                                logging.warning("package '%s' version '%s' hints changed\n%s" % (p, vr, diff))

                    # XXX: we should really do something complex here, like
                    # assign the legacy hints from b to all vr in a which didn't
                    # have a pvr.hint.  Instead, just report if it's going to
                    # change and let things get sorted out later on...
                    if a[p].legacy_hints and b[p].legacy_hints and a[p].legacy_hints != b[p].legacy_hints:
                        diff = '\n'.join(difflib.ndiff(
                            pprint.pformat(a[p].legacy_hints).splitlines(),
                            pprint.pformat(b[p].legacy_hints).splitlines()))
                        logging.warning("package '%s' hints changed\n%s" % (p, diff))

                    # overrides from b take precedence
                    c[p].override_hints.update(b[p].override_hints)

                    # merge hint file lists
                    c[p].hint_files.update(b[p].hint_files)

                    # skip if both a and b are skip
                    c[p].skip = a[p].skip and b[p].skip

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
# helper function to mark a package version as fresh (not stale)
#

def mark_package_fresh(packages, p, v):
    if 'install' in packages[p].vermap[v]:
        packages[p].tars[packages[p].vermap[v]['install']].fresh = True

    if 'source' in packages[p].vermap[v]:
        packages[p].tars[packages[p].vermap[v]['source']].fresh = True
        return

    # unless the install tarfile is empty ...
    if 'install' not in packages[p].vermap[v]:
        return

    if packages[p].tars[packages[p].vermap[v]['install']].is_empty:
        return

    # ... mark any corresponding external-source package version as also fresh
    if 'external-source' in packages[p].version_hints[v]:
        es_p = packages[p].version_hints[v]['external-source']
        if es_p in packages:
            if 'source' in packages[es_p].vermap[v]:
                packages[es_p].tars[packages[es_p].vermap[v]['source']].fresh = True


#
# construct a move list of stale packages
#

def stale_packages(packages):
    for pn, po in packages.items():
        # mark any versions used by stability levels as fresh
        for level in ['curr', 'prev', 'test']:
            if level in po.stability:
                v = po.stability[level]
                mark_package_fresh(packages, pn, v)

        # mark any versions explicitly listed in the keep: override hint
        for v in po.override_hints.get('keep', '').split():
            if v in po.vermap:
                mark_package_fresh(packages, pn, v)
            else:
                logging.error("package '%s' has non-existent keep: version '%s'" % (pn, v))

        # mark as fresh the highest n versions, where n is given by the
        # keep-count: override hint, (defaulting to DEFAULT_KEEP_COUNT)
        keep_count = int(po.override_hints.get('keep-count', common_constants.DEFAULT_KEEP_COUNT))
        for v in sorted(po.vermap.keys(), key=lambda v: SetupVersion(v), reverse=True)[0:keep_count]:
            mark_package_fresh(packages, pn, v)

        # mark as fresh all versions after the first one which is newer than
        # the keep-days: override hint, (defaulting to DEFAULT_KEEP_DAYS)
        # (as opposed to checking the mtime for each version to determine if
        # it is included)
        keep_days = po.override_hints.get('keep-days', common_constants.DEFAULT_KEEP_DAYS)
        newer = False
        for v in sorted(po.vermap.keys(), key=lambda v: SetupVersion(v)):
            if not newer:
                if 'install' in po.vermap[v]:
                    if po.tars[po.vermap[v]['install']].mtime > (time.time() - (keep_days * 24 * 60 * 60)):
                        newer = True

            if newer:
                mark_package_fresh(packages, pn, v)

    # build a move list of stale versions
    stale = defaultdict(list)
    for pn, po in packages.items():
        for v in sorted(po.vermap.keys(), key=lambda v: SetupVersion(v)):
            all_stale = True
            for category in ['source', 'install']:
                if category in po.vermap[v]:
                    if not getattr(po.tars[po.vermap[v][category]], 'fresh', False):
                        stale[po.path].append(po.vermap[v][category])
                        logging.debug("package '%s' version '%s' %s is stale" % (pn, v, category))
                    else:
                        all_stale = False

            # if there's a pvr.hint without a fresh source or install of the
            # same version, move it as well
            if all_stale:
                if v in po.hint_files:
                    stale[po.path].append(po.hint_files[v])
                    logging.debug("package '%s' version '%s' hint is stale" % (pn, v))

        # clean up freshness mark
        for v in po.vermap:
            for c in po.vermap[v]:
                try:
                    delattr(po.tars[po.vermap[v][c]], 'fresh')
                except AttributeError:
                    pass

    return stale

#
#
#
if __name__ == "__main__":
    for arch in common_constants.ARCHES:
        packages = read_packages(common_constants.FTP, arch)
        print("arch %s has %d packages" % (arch, len(packages)))

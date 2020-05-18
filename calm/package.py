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
from enum import Enum, unique
import copy
import difflib
import hashlib
import json
import logging
import os
import pprint
import re
import tarfile
import textwrap
import time

from .version import SetupVersion
from .movelist import MoveList
from . import common_constants
from . import hint
from . import maintainers
from . import past_mistakes


# kinds of packages
@unique
class Kind(Enum):
    binary = 1  # aka 'install'
    source = 2


# information we keep about a package
class Package(object):
    def __init__(self):
        self.pkgpath = ''  # path to package, relative to arch
        self.tars = {}
        self.hints = {}
        self.is_used_by = set()
        self.version_hints = {}
        self.override_hints = {}
        self.skip = False
        self.vermap = {}

    def __repr__(self):
        return "Package('%s', %s, %s, %s, %s)" % (
            self.pkgpath,
            pprint.pformat(self.tars),
            pprint.pformat(self.version_hints),
            pprint.pformat(self.override_hints),
            self.skip)

    def tar(self, vr, category):
        return self.tars[vr][self.vermap[vr][category]]


# information we keep about a tar file
class Tar(object):
    def __init__(self):
        self.path = None  # path to tar, relative to release area
        self.fn = None    # filename
        self.sha512 = ''
        self.size = 0
        self.is_empty = False
        self.is_used = False

    def __repr__(self):
        return "Tar('%s', '%s', '%s', %d, %s)" % (self.fn, self.path, self.sha512, self.size, self.is_empty)


# information we keep about a hint file
class Hint(object):
    def __init__(self):
        self.path = None  # path to hint, relative to release area
        self.fn = None    # filename of hint
        self.hints = {}   # XXX: duplicates version_hints, for the moment


#
# read a packages from a directory hierarchy
#
def read_packages(rel_area, arch):
    packages = {}

    # <arch>/ noarch/ and src/ directories are considered
    for root in ['noarch', 'src', arch]:
        packages[root] = {}

        releasedir = os.path.join(rel_area, root)
        logging.debug('reading packages from %s' % releasedir)

        for (dirpath, subdirs, files) in os.walk(releasedir, followlinks=True):
            read_package_dir(packages[root], rel_area, dirpath, files)

        logging.debug("%d packages read from %s" % (len(packages[root]), releasedir))

    return merge({}, *packages.values())


# helper function to compute sha512 for a particular file
# (block_size should be some multiple of sha512 block size which can be efficiently read)
def sha512_file(fn, block_size=256 * 128):
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

    # if we don't have both requires: and depends:, generate the one
    # from the other
    if ('requires' in hints) and ('depends' not in hints):
        hints['depends'] = ', '.join(hints['requires'].split())
    elif ('depends' in hints) and ('requires' not in hints):
        hints['requires'] = ' '.join([re.sub(r'(.*)\s+\(.*\)', r'\1', d) for d in hints['depends'].split(',')])

    return hints


# helper function to clean up hints
def clean_hints(p, hints, warnings):
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
                logging.error("package '%s' sdesc starts with '%s'; this is redundant as the UI will show both the package name and sdesc" % (p, ''.join(colon.group(1, 2))))
                warnings = True

    return warnings


#
# read a single package directory
#
# (may contain at most one source package and one binary package)
# (return True if problems, False otherwise)
#

def read_package_dir(packages, basedir, dirpath, files, remove=[], upload=False):
    relpath = os.path.relpath(dirpath, basedir)

    # the package name is always the directory name
    p = os.path.basename(dirpath)

    # no .hint files
    if not any([f.endswith('.hint') for f in files]):
        if (relpath.count(os.path.sep) > 1):
            for s in ['md5.sum', 'sha512.sum']:
                if s in files:
                    files.remove(s)

            if len(files) > 0:
                logging.error("no .hint files in %s but has files: %s" % (dirpath, ', '.join(files)))
                return True

        return False

    # discard obsolete md5.sum
    if 'md5.sum' in files:
        files.remove('md5.sum')

    # ignore dotfiles and backup files
    for f in files[:]:
        if f.startswith('.') or f.endswith('.bak'):
            files.remove(f)

    # classify files for which kind of package they belong to
    fl = {}
    for kind in list(Kind) + ['all']:
        fl[kind] = []

    for f in files[:]:
        if f == 'sha512.sum' or f == 'override.hint':
            fl['all'].append(f)
            files.remove(f)
        elif re.match(r'^' + re.escape(p) + r'.*\.hint$', f):
            if f.endswith('-src.hint'):
                fl[Kind.source].append(f)
            else:
                fl[Kind.binary].append(f)
            files.remove(f)
        elif re.match(r'^' + re.escape(p) + r'.*\.tar\.(bz2|gz|lzma|xz)$', f):
            if '-src.tar' in f:
                fl[Kind.source].append(f)
            else:
                fl[Kind.binary].append(f)
            files.remove(f)

    # read package
    result = False
    for kind in Kind:
        # only create a package if there's archives for it to contain
        if fl[kind]:
            result = read_one_package(packages, p, relpath, dirpath, fl[kind] + fl['all'], remove, kind) or result

    # warn about unexpected files, including tarfiles which don't match the
    # package name
    if files:
        logging.error("unexpected files in %s: %s" % (p, ', '.join(files)))
        result = True

    return result


#
# read a single package
#
def read_one_package(packages, p, relpath, dirpath, files, remove, kind):
    warnings = False

    if not re.match(r'^[\w\-._+]*$', p):
        logging.error("package '%s' name contains illegal characters" % p)
        return True

    # assumption: no real package names end with '-src'
    #
    # enforce this, because source and install package names exist in a
    # single namespace currently, and otherwise there could be a collision
    if p.endswith('-src'):
        logging.error("package '%s' name ends with '-src'" % p)
        return True

    # check for duplicate package names at different paths
    (_, _, pkgpath) = relpath.split(os.sep, 2)
    pn = p + ('-src' if kind == Kind.source else '')

    if pn in packages:
        logging.error("duplicate package name at paths %s and %s" %
                      (relpath, packages[p].pkgpath))
        return True

    # determine version overrides
    note_absent = ('override.hint' in remove) or ('override.hint' in files)

    if 'override.hint' in files:
        # read override.hint
        override_hints = read_hints(p, os.path.join(dirpath, 'override.hint'), hint.override)
        if override_hints is None:
            logging.error("error parsing %s" % (os.path.join(dirpath, 'override.hint')))
            return True
        files.remove('override.hint')
    else:
        override_hints = {}

    # if override.hint exists or is being removed, explicitly note absent
    # stability level hints
    if note_absent:
        for level in ['test', 'curr', 'prev']:
            if level not in override_hints:
                override_hints[level] = None

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
                    logging.warning("bad line '%s' in sha512.sum for package '%s'" % (l.strip(), p))

    # build a list of version-releases (since replacement pvr.hint files are
    # allowed to be uploaded, we must consider both .tar and .hint files for
    # that), and collect the attributes for each tar file
    tars = defaultdict(dict)
    vr_list = set()

    for f in list(files):
        # warn if filename doesn't follow P-V-R naming convention
        #
        # P must match the package name, V can contain anything, R must
        # start with a number
        match = re.match(r'^' + re.escape(p) + r'-(.+)-(\d[0-9a-zA-Z.]*)(-src|)\.(tar\.(bz2|gz|lzma|xz)|hint)$', f)
        if not match:
            logging.error("file '%s' in package '%s' doesn't follow naming convention" % (f, p))
            return True
        else:
            v = match.group(1)
            r = match.group(2)

            # historically, V can contain a '-' (since we can use the fact
            # we already know P to split unambiguously), but this is a bad
            # idea.
            if '-' in v:
                if v in past_mistakes.hyphen_in_version.get(p, []):
                    lvl = logging.INFO
                else:
                    lvl = logging.ERROR
                    warnings = True
                logging.log(lvl, "file '%s' in package '%s' contains '-' in version" % (f, p))

            if not v[0].isdigit():
                logging.error("file '%s' in package '%s' has a version which doesn't start with a digit" % (f, p))
                warnings = True

            # if not there already, add to version-release list
            vr = '%s-%s' % (v, r)
            vr_list.add(vr)

        if not f.endswith('.hint'):
            # collect the attributes for each tar file
            t = Tar()
            t.path = relpath
            t.fn = f
            t.size = os.path.getsize(os.path.join(dirpath, f))
            t.is_empty = tarfile_is_empty(os.path.join(dirpath, f))
            t.mtime = os.path.getmtime(os.path.join(dirpath, f))

            if f in sha512:
                t.sha512 = sha512[f]
            else:
                t.sha512 = sha512_file(os.path.join(dirpath, f))
                logging.debug("no sha512.sum line for file %s in package '%s', computed sha512 hash is %s" % (f, p, t.sha512))

            tars[vr][f] = t

    # determine hints for each version we've encountered
    version_hints = {}
    hints = {}
    actual_tars = {}
    for vr in vr_list:
        hint_fn = '%s-%s%s.hint' % (p, vr, '-src' if kind == Kind.source else '')
        if hint_fn in files:
            # is there a PVR.hint file?
            pvr_hint = read_hints(p, os.path.join(dirpath, hint_fn), hint.pvr if kind == Kind.binary else hint.spvr)
            if not pvr_hint:
                logging.error("error parsing %s" % (os.path.join(dirpath, hint_fn)))
                return True
            warnings = clean_hints(p, pvr_hint, warnings)
        else:
            # it's an error to not have a pvr.hint
            logging.error("package %s has packages for version %s, but no %s" % (p, vr, hint_fn))
            return True

        # apply a version override
        if 'version' in pvr_hint:
            ovr = pvr_hint['version']
        else:
            ovr = vr

        # external source will always point to a source package
        if 'external-source' in pvr_hint:
            pvr_hint['external-source'] += '-src'

        hintobj = Hint()
        hintobj.path = relpath
        hintobj.fn = hint_fn
        hintobj.hints = pvr_hint

        version_hints[ovr] = pvr_hint
        hints[ovr] = hintobj
        actual_tars[ovr] = tars[vr]

    packages[pn] = Package()
    packages[pn].version_hints = version_hints
    packages[pn].override_hints = override_hints
    packages[pn].tars = actual_tars
    packages[pn].hints = hints
    packages[pn].pkgpath = pkgpath
    if kind == Kind.source:
        packages[pn].skip = True
    else:
        packages[pn].skip = any(['skip' in version_hints[vr] for vr in version_hints])
    packages[pn].kind = kind
    # since we are kind of inventing the source package names, and don't
    # want to report them, keep track of the real name
    packages[pn].orig_name = p

    return warnings


#
# utility to determine if a tar file is empty
#
def tarfile_is_empty(tf):
    size = os.path.getsize(tf)

    # report invalid files (smaller than the smallest possible compressed file
    # for any of the compressions we support)
    if size < 14:
        logging.error("tar archive %s is too small (%d bytes)" % (tf, size))
        return True

    # sometimes compressed empty files are used rather than a compressed empty
    # tar archive
    if size <= 32:
        return True

    # parsing the tar archive just to determine if it contains at least one
    # archive member is relatively expensive, so we just assume it contains
    # something if it's over a certain size threshold
    if size > 1024:
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

    if packages is None:
        return False

    for p in sorted(packages.keys()):
        logging.log(5, "validating package '%s'" % (p))
        has_requires = False

        for (v, hints) in packages[p].version_hints.items():
            for (c, okmissing, splitchar) in [
                    ('requires', 'missing-required-package', None),
                    ('depends', 'missing-depended-package', ','),
                    ('obsoletes', 'missing-obsoleted-package', ',')
            ]:
                # if c is in hints, and not the empty string
                if hints.get(c, ''):
                    for r in hints[c].split(splitchar):
                        if c == 'requires':
                            has_requires = True

                        # remove any extraneous whitespace
                        r = r.strip()

                        # strip off any version relation enclosed in '()'
                        # following the package name
                        if splitchar:
                            r = re.sub(r'(.*) +\(.*\)', r'\1', r)

                        # a package should not appear in it's own hint
                        if r == p:
                            lvl = logging.WARNING if p not in past_mistakes.self_requires else logging.DEBUG
                            logging.log(lvl, "package '%s' version '%s' %s itself" % (p, v, c))

                        # all packages listed in a hint must exist (unless the
                        # disable-check option says that's ok)
                        if r not in packages:
                            if okmissing not in getattr(args, 'disable_check', []):
                                logging.error("package '%s' version '%s' %s nonexistent or errored package '%s'" % (p, v, c, r))
                                error = True
                            continue

                        # hint referencing a source-only package makes no sense
                        if packages[r].skip:
                            logging.error("package '%s' version '%s' %s source-only package '%s'" % (p, v, c, r))
                            error = True

            # if external-source is used, the package must exist
            if 'external-source' in hints:
                e = hints['external-source']
                if e not in packages:
                    logging.error("package '%s' version '%s' refers to nonexistent or errored external-source '%s'" % (p, v, e))
                    error = True

        # If package A is obsoleted by package B, B should appear in the
        # requires: for A (so the upgrade occurs with pre-depends: aware
        # versions of setup), but not in the depends: for A (as that creates an
        # unsatisfiable dependency when explicitly installing A with lisolv
        # versions of setup, which should just install B).  This condition can
        # occur since we might have synthesized the depends: from the requires:
        # in read_hints(), so fix that up here.
        for (v, hints) in packages[p].version_hints.items():
            obsoletes = hints.get('obsoletes', '')
            if obsoletes:
                for o in obsoletes.split(','):
                    o = o.strip()
                    o = re.sub(r'(.*) +\(.*\)', r'\1', o)

                    if o in packages:
                        for (ov, ohints) in packages[o].version_hints.items():
                            if 'depends' in ohints:
                                depends = ohints['depends'].split(',')
                                if p in depends:
                                    depends = [d for d in depends if d != p]
                                    packages[o].version_hints[ov]['depends'] = ','.join(depends)
                                    logging.debug("removed obsoleting '%s' from the depends: of package '%s'" % (p, o))
                    else:
                        logging.debug("can't ensure package '%s' doesn't depends: on obsoleting '%s'" % (o, p))

        packages[p].vermap = {}
        is_empty = {}
        has_source = False
        has_install = False
        has_nonempty_install = False

        for vr in packages[p].tars:
            for (t, tar) in packages[p].tars[vr].items():
                # categorize each tarfile as either 'source' or 'install'
                if re.search(r'-src.*\.tar', t):
                    category = 'source'
                    has_source = True
                else:
                    category = 'install'
                    has_install = True
                    is_empty[t] = packages[p].tars[vr][t].is_empty
                    if not is_empty[t]:
                        has_nonempty_install = True

                if vr not in packages[p].vermap:
                    packages[p].vermap[vr] = {}

                # for each version, a package can contain at most one source tar
                # file and at most one install tar file.  warn if we have too many
                # (for e.g. both a .xz and .bz2 install tar file)
                if category in packages[p].vermap[vr]:
                    logging.error("package '%s' has more than one %s tar file for version '%s'" % (p, category, vr))
                    error = True

                # store tarfile corresponding to this version and category
                packages[p].vermap[vr][category] = t
                packages[p].vermap[vr]['mtime'] = tar.mtime

        # check that package only contains tar archives of the appropriate type
        if packages[p].kind == Kind.source:
            if has_install:
                logging.error("source package '%s' has install archives" % (p))
                error = True
        elif packages[p].kind == Kind.binary:
            if has_source:
                logging.error("package '%s' has source archives" % (p))
                error = True

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
            packages[p].version_hints[v][l] = ''
            # and remove from list of unallocated levels
            levels.remove(l)

        # lastly, fill in any levels which we skipped over because a higher
        # stability level was overriden to a lower version
        for l in levels:
            if l in packages[p].override_hints:
                if packages[p].override_hints[l] is not None:
                    packages[p].stability[l] = packages[p].override_hints[l]

        l = 'test'
        if l not in packages[p].stability:
            for v in sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
                if 'test' in packages[p].version_hints[v]:
                    packages[p].stability[l] = v
                    packages[p].version_hints[v][l] = ''
                    break

        # identify a 'best' version to take certain information from: this is
        # the curr version, if we have one, otherwise, the highest version.
        if ('curr' in packages[p].stability) and (packages[p].stability['curr'] in packages[p].vermap):
            packages[p].best_version = packages[p].stability['curr']
        elif len(packages[p].vermap):
            packages[p].best_version = sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True)[0]
        else:
            logging.error("package '%s' doesn't have any versions" % (p))
            packages[p].best_version = None
            error = True

        # the package must have some versions
        if not packages[p].stability:
            logging.error("no versions at any stability level for package '%s'" % (p))
            error = True
        # it's also probably a really good idea if a curr version exists
        elif (('curr' not in packages[p].stability) and
              ('missing-curr' not in packages[p].version_hints[packages[p].best_version].get('disable-check', '')) and
              ('missing-curr' not in getattr(args, 'disable_check', []))):
            logging.warning("package '%s' doesn't have a curr version" % (p))

        # error if the curr: version isn't the most recent non-test: version
        for v in sorted(packages[p].vermap.keys(), key=lambda v: packages[p].vermap[v]['mtime'], reverse=True):
            if 'test' in packages[p].version_hints[v]:
                continue

            cv = packages[p].stability['curr']

            if cv not in packages[p].vermap:
                continue

            if cv != v:
                if packages[p].vermap[v]['mtime'] == packages[p].vermap[cv]['mtime']:
                    # don't consider an equal mtime to be more recent
                    continue

                if ((p in past_mistakes.mtime_anomalies) or
                    ('curr-most-recent' in packages[p].override_hints.get('disable-check', '')) or
                    ('curr-most-recent' in getattr(args, 'disable_check', []))):
                    lvl = logging.DEBUG
                else:
                    lvl = logging.ERROR
                    error = True
                logging.log(lvl, "package '%s' version '%s' is most recent non-test version, but version '%s' is curr:" % (p, v, cv))

            break

        if 'replace-versions' in packages[p].override_hints:
            for rv in packages[p].override_hints['replace-versions'].split():
                # warn if replace-versions lists a version which is less than
                # the current version (which is pointless as the current version
                # will replace it anyhow)
                if packages[p].best_version:
                    if SetupVersion(rv) <= SetupVersion(packages[p].best_version):
                        logging.warning("package '%s' replace-versions: uselessly lists version '%s', which is <= current version" % (p, rv))

                # warn if replace-versions lists a version which is also
                # available to install (as this doesn't work as expected)
                if rv in packages[p].version_hints:
                    logging.warning("package '%s' replace-versions: lists version '%s', which is also available to install" % (p, rv))

        # If the install tarball is empty and there is no source tarball, we
        # should probably be marked obsolete
        if not packages[p].skip:
            for vr in packages[p].version_hints:
                if '_obsolete' not in packages[p].version_hints[vr].get('category', '') and vr in packages[p].vermap:
                    if ('source' not in packages[p].vermap[vr]) and ('external-source' not in packages[p].version_hints[vr]):
                        if 'install' in packages[p].vermap[vr]:
                            if packages[p].tar(vr, 'install').is_empty:
                                if ((vr in past_mistakes.empty_but_not_obsolete.get(p, [])) or
                                    ('empty-obsolete' in packages[p].version_hints[vr].get('disable-check', ''))):
                                    lvl = logging.DEBUG
                                else:
                                    if 'external-source' in packages[p].version_hints[vr]:
                                        lvl = logging.ERROR
                                        error = True
                                    else:
                                        lvl = logging.WARNING
                                logging.log(lvl, "package '%s' version '%s' has empty install tar file, but it's not in the _obsolete category" % (p, vr))

    # make another pass to verify a source tarfile exists for every install
    # tarfile version
    for p in sorted(packages.keys()):
        for v in sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
            if 'install' not in packages[p].vermap[v]:
                continue

            sourceless = False
            missing_source = True

            # source tarfile is in the external-source package, if specified,
            # otherwise it's in the sibling source package
            if 'external-source' in packages[p].version_hints[v]:
                es_p = packages[p].version_hints[v]['external-source']
            else:
                es_p = p + '-src'

            # mark the source tarfile as being used by an install tarfile
            if es_p in packages:
                if v in packages[es_p].vermap and 'source' in packages[es_p].vermap[v]:
                    packages[es_p].tar(v, 'source').is_used = True
                    packages[es_p].is_used_by.add(p)
                    missing_source = False

            if missing_source:
                # unless the install tarfile is empty
                if packages[p].tar(v, 'install').is_empty:
                    sourceless = True
                    missing_source = False

                # unless this package is marked as 'self-source'
                if p in past_mistakes.self_source:
                    sourceless = True
                    missing_source = False

            # ... it's an error for this package to be missing source
            packages[p].tar(v, 'install').sourceless = sourceless
            if missing_source:
                logging.error("package '%s' version '%s' is missing source" % (p, v))
                error = True

    # make another pass to verify that each non-empty source tarfile version has
    # at least one corresponding non-empty install tarfile, in some package.
    for p in sorted(packages.keys()):
        for v in sorted(packages[p].vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
            if 'source' not in packages[p].vermap[v]:
                continue

            if packages[p].tar(v, 'source').is_empty:
                continue

            if '_obsolete' in packages[p].version_hints[v].get('category', ''):
                continue

            if not packages[p].tar(v, 'source').is_used:
                logging.error("package '%s' version '%s' source has no non-empty install tarfiles" % (p, v))
                error = True

    # do all the packages which use this source package have the same
    # current version?
    for source_p in sorted(packages.keys()):
        versions = defaultdict(list)

        for install_p in packages[source_p].is_used_by:
            # ignore obsolete packages
            if any(['_obsolete' in packages[install_p].version_hints[vr].get('category', '') for vr in packages[install_p].version_hints]):
                continue

            # ignore runtime library packages, as we may keep old versions of
            # those
            if re.match(r'^lib.*\d', install_p):
                continue

            # ignore Python module packages, as we may keep old versions of
            # those
            if re.match(r'^python[23][567]-.*', install_p):
                continue

            # ignore packages which don't have a current version (i.e. are test
            # only)
            if 'curr' not in packages[install_p].stability:
                continue

            # ignore specific packages we disable this check for
            if ((install_p in past_mistakes.nonunique_versions) or
                ('unique-version' in packages[install_p].version_hints[packages[install_p].best_version].get('disable-check', ''))):
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
            logging.error("install packages from source package '%s' have non-unique current versions %s" % (packages[source_p].orig_name, ', '.join(reversed(out))))

    # validate that all packages are in the package maintainers list
    error = validate_package_maintainers(args, packages) or error

    return not error


#
def validate_package_maintainers(args, packages):
    error = False
    if not args.pkglist:
        return error

    # read maintainer list
    mlist = {}
    mlist = maintainers.Maintainer.add_packages(mlist, args.pkglist)

    # make the list of all packages
    all_packages = maintainers.Maintainer.all_packages(mlist)

    # validate that all packages are in the package list
    for p in sorted(packages):
        # ignore obsolete packages
        if any(['_obsolete' in packages[p].version_hints[vr].get('category', '') for vr in packages[p].version_hints]):
            continue
        # validate that the package is in a path which starts with something in the package list
        if not is_in_package_list(packages[p].pkgpath, all_packages):
            logging.error("package '%s' on path '%s', which doesn't start with a package in the package list" % (p, packages[p].pkgpath))
            error = True
        # source which is superseded by a different package, but retained due to
        # old install versions can be unmaintained and non-obsolete
        if packages[p].kind == Kind.source:
            continue
        # validate that the source package has a maintainer
        bv = packages[p].best_version
        if bv:
            es = packages[p].version_hints[bv].get('external-source', p)
            if es in packages:
                es_pn = packages[es].orig_name
                if es_pn not in all_packages and p not in all_packages:
                    if bv not in past_mistakes.maint_anomalies.get(p, []):
                        logging.error("package '%s' is not obsolete, but has no maintainer" % (p))
                        error = True

    return error


#
# write setup.ini
#
def write_setup_ini(args, packages, arch):

    logging.debug('writing %s' % (args.inifile))

    with open(args.inifile, 'w') as f:
        tz = time.time()
        # write setup.ini header
        print(textwrap.dedent('''\
        # This file was automatically generated at %s.
        #
        # If you edit it, your edits will be discarded next time the file is
        # generated.
        #
        # See https://sourceware.org/cygwin-apps/setup.ini.html for a description
        # of the format.''')
              % (time.strftime("%F %T %Z", time.localtime(tz))),
              file=f)

        if args.release:
            print("release: %s" % args.release, file=f)
        print("arch: %s" % arch, file=f)
        print("setup-timestamp: %d" % tz, file=f)

        if args.setup_version:
            # this token exists in the lexer, but not in the grammar up until
            # 2.878 (when it was removed), so will cause a parse error with
            # versions prior to that.
            print("include-setup: setup <2.878 not supported", file=f)

            # not implemented until 2.890, ignored by earlier versions
            print("setup-minimum-version: 2.878", file=f)

            # for setup to check if a setup upgrade is possible
            print("setup-version: %s" % args.setup_version, file=f)

        # for each package
        for pn in sorted(packages, key=sort_key):
            po = packages[pn]

            # do nothing if 'skip'
            if po.skip:
                continue

            # write package data
            print("\n@ %s" % pn, file=f)

            bv = po.best_version
            print("sdesc: %s" % po.version_hints[bv]['sdesc'], file=f)

            if 'ldesc' in po.version_hints[bv]:
                print("ldesc: %s" % po.version_hints[bv]['ldesc'], file=f)

            # for historical reasons, category names must start with a capital
            # letter
            category = ' '.join(map(upper_first_character, po.version_hints[bv]['category'].split()))
            print("category: %s" % category, file=f)

            # compute the union of requires for all versions
            requires = set()
            for hints in po.version_hints.values():
                if 'requires' in hints:
                    requires = set.union(requires, hints['requires'].split())
            # empty requires are suppressed as setup's parser can't handle that
            if requires:
                print("requires: %s" % ' '.join(sorted(requires)), file=f)

            if 'message' in po.version_hints[bv]:
                print("message: %s" % po.version_hints[bv]['message'], file=f)

            if 'replace-versions' in po.override_hints:
                print("replace-versions: %s" % po.override_hints['replace-versions'], file=f)

            # make a list of version sections
            #
            # (they are put in a particular order to ensure certain behaviour
            # from setup)
            vs = []

            # put 'curr' first
            #
            # due to a historic bug in setup (fixed in 78e4c7d7), we keep the
            # [curr] version first, to ensure that dependencies are used
            # correctly.
            if 'curr' in po.stability:
                version = po.stability['curr']
                vs.append((version, 'curr'))

            # next put any other versions
            #
            # these [prev] or [test] sections are superseded by the final ones.
            #
            # (to maintain historical behaviour, include versions which only
            # exist as a source package)
            #
            versions = set(po.vermap.keys())
            sibling_src = pn + '-src'
            if sibling_src in packages:
                versions.update(packages[sibling_src].vermap.keys())

            for version in sorted(versions, key=lambda v: SetupVersion(v), reverse=True):
                # skip over versions assigned to stability level: 'curr' has
                # already be done, and 'prev' and 'test' will be done later
                skip = False
                for level in ['curr', 'prev', 'test']:
                    if level in po.stability:
                        if version == po.stability[level]:
                            skip = True
                            break

                if skip:
                    continue

                # test versions receive the test label
                if 'test' in po.version_hints.get(version, {}):
                    level = "test"
                else:
                    level = "prev"
                vs.append((version, level))

            # finally, add 'prev' and 'test' versions
            #
            # because setup processes version sections in order, these supersede
            # any previous [prev] and [test] sections (hopefully).  i.e. the
            # version in the final [test] section is the one selected when test
            # packages are requested.
            for level in ['prev', 'test']:
                if level in po.stability:
                    version = po.stability[level]
                    vs.append((version, level))

            # write the section for each version
            for (version, tag) in vs:
                # [curr] can be omitted if it's the first section
                if tag != 'curr':
                    print("[%s]" % tag, file=f)
                print("version: %s" % version, file=f)

                is_empty = False
                if 'install' in po.vermap.get(version, {}):
                    tar_line(po, 'install', version, f)
                    is_empty = po.tar(version, 'install').is_empty

                hints = po.version_hints.get(version, {})

                # follow external-source
                if 'external-source' in hints:
                    s = hints['external-source']
                else:
                    s = sibling_src
                    if s not in packages:
                        s = None

                # external-source points to a source file in another package
                if s:
                    if 'source' in packages[s].vermap.get(version, {}):
                        tar_line(packages[s], 'source', version, f)
                    else:
                        if not (is_empty or packages[s].orig_name in past_mistakes.self_source):
                            logging.warning("package '%s' version '%s' has no source in '%s'" % (pn, version, packages[s].orig_name))

                # external-source should also be capable of pointing to a 'real'
                # source package (if cygport could generate such a thing), in
                # which case we should emit a 'Source:' line, and the package is
                # also itself emitted.

                if hints.get('depends', '') or requires:
                    print("depends2: %s" % hints.get('depends', ''), file=f)

                if hints.get('obsoletes', ''):
                    print("obsoletes: %s" % hints['obsoletes'], file=f)

                if hints.get('build-depends', ''):
                    bd = hints['build-depends']

                    # Ideally, we'd transform dependency atoms which aren't
                    # cygwin package names into package names. For the moment,
                    # we don't have the information to do that, so filter them
                    # all out.
                    bd = [atom for atom in bd.split(', ') if '(' not in atom]

                    if bd:
                        print("build-depends: %s" % ', '.join(bd), file=f)

                if hints.get('provides', ''):
                    print("provides: %s" % hints['provides'], file=f)

                if hints.get('conflicts', ''):
                    print("conflicts: %s" % hints['conflicts'], file=f)


# helper function to output details for a particular tar file
def tar_line(p, category, v, f):
    to = p.tar(v, category)
    fn = os.path.join(to.path, to.fn)
    sha512 = to.sha512
    size = to.size
    print("%s: %s %d %s" % (category, fn, size, sha512), file=f)


# helper function to change the first character of a string to upper case,
# without altering the rest
def upper_first_character(s):
    return s[:1].upper() + s[1:]


#
# write a json summary of packages
#
def write_repo_json(args, packages, f):
    package_list = set()
    for arch in packages:
        package_list.update(packages[arch])

    mlist = maintainers.Maintainer.read(args, None)
    pkg_maintainers = maintainers.Maintainer.invert(mlist)

    pl = []
    for pn in sorted(package_list):
        po = None
        arches = []
        for arch in common_constants.ARCHES:
            if pn in packages[arch]:
                po = packages[arch][pn]
                arches.append(arch)

        def package(p):
            for arch in common_constants.ARCHES:
                if p in packages[arch]:
                    return packages[arch][p]
            return None

        bv = po.best_version

        if po.kind != Kind.source:
            continue

        versions = {}
        for vr in sorted(po.version_hints.keys(), key=lambda v: SetupVersion(v)):
            key = 'test' if 'test' in po.version_hints[vr] else 'stable'
            versions[key] = versions.get(key, []) + [vr]

        d = {
            'name': po.orig_name,
            'versions': versions,
            'summary': po.version_hints[bv]['sdesc'].strip('"'),
            'subpackages': [{'name': sp, 'categories': package(sp).version_hints[package(sp).best_version].get('category', '').split()} for sp in sorted(po.is_used_by)],
            'arches': arches,
        }

        if 'homepage' in po.version_hints[bv]:
            d['homepage'] = po.version_hints[bv]['homepage']

        if pkg_maintainers[po.orig_name] and ('ORPHANED' not in pkg_maintainers[po.orig_name]):
            d['maintainers'] = sorted(pkg_maintainers[po.orig_name])

        pl.append(d)

    j = {
        'repository_name': args.release,
        'timestamp': int(time.time()),
        'num_packages': len(pl),
        'packages': pl,
    }
    json.dump(j, f)


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
            if p not in c:
                c[p] = b[p]
            # else, if the package is both in a and b, we have to do a merge
            else:
                # package must exist at same relative path
                if c[p].pkgpath != b[p].pkgpath:
                    logging.error("package '%s' is at paths %s and %s" % (p, c[p].pkgpath, b[p].pkgpath))
                    return None
                else:
                    for vr in b[p].tars:
                        if vr in c[p].tars:
                            for t in b[p].tars[vr]:
                                if t in c[p].tars[vr]:
                                    logging.error("package '%s' has duplicate tarfile %s for version %s" % (p, t, vr))
                                    return None
                                else:
                                    c[p].tars[vr][t] = b[p].tars[vr][t]
                        else:
                            c[p].tars[vr] = b[p].tars[vr]

                    # hints from b override hints from a, but warn if they have
                    # changed
                    for vr in b[p].version_hints:
                        c[p].version_hints[vr] = b[p].version_hints[vr]
                        if vr in c[p].version_hints:
                            if c[p].version_hints[vr] != b[p].version_hints[vr]:
                                diff = '\n'.join(difflib.ndiff(
                                    pprint.pformat(c[p].version_hints[vr]).splitlines(),
                                    pprint.pformat(b[p].version_hints[vr]).splitlines()))

                                logging.warning("package '%s' version '%s' hints changed\n%s" % (p, vr, diff))

                    # overrides from b take precedence
                    c[p].override_hints.update(b[p].override_hints)

                    # merge hint file lists
                    c[p].hints.update(b[p].hints)

                    # skip if both a and b are skip
                    c[p].skip = c[p].skip and b[p].skip

    return c


#
# delete a file from a package set
#

def delete(packages, path, fn):
    (_, _, pkgpath) = path.split(os.sep, 2)
    for p in packages:
        if packages[p].pkgpath == pkgpath:
            for vr in packages[p].tars:
                for t in packages[p].tars[vr]:
                    if t == fn:
                        del packages[p].tars[vr][t]
                        break

                # if no packages remain for this vr, also remove from vermap
                if not packages[p].tars[vr]:
                    packages[p].vermap.pop(vr, None)

            for h in packages[p].hints:
                if packages[p].hints[h].fn == fn:
                    del packages[p].hints[h]
                    break


#
# verify that the package path starts with a package in the list of packages
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


def is_in_package_list(ppath, plist):
    superpackage = ppath.split(os.sep, 1)[0]
    return superpackage in plist


#
# helper function to mark a package version as fresh (not stale)
#

def mark_package_fresh(packages, p, v):
    if 'install' in packages[p].vermap[v]:
        packages[p].tar(v, 'install').fresh = True

    # ... mark any corresponding sibling or external-source package version as also fresh
    if 'external-source' in packages[p].version_hints[v]:
        es_p = packages[p].version_hints[v]['external-source']
    else:
        es_p = p + '-src'

    if es_p in packages:
        if v in packages[es_p].vermap:
            if 'source' in packages[es_p].vermap[v]:
                packages[es_p].tar(v, 'source').fresh = True


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

        # mark as fresh the highest n non-test versions, where n is given by the
        # keep-count: override hint, (defaulting to DEFAULT_KEEP_COUNT)
        keep_count = int(po.override_hints.get('keep-count', common_constants.DEFAULT_KEEP_COUNT))
        for v in sorted(po.vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
            if 'test' not in po.version_hints[v]:
                if keep_count <= 0:
                    break
                mark_package_fresh(packages, pn, v)
                keep_count = keep_count - 1

        # mark as fresh the highest n test versions, where n is given by the
        # keep-count-test: override hint, (defaulting to DEFAULT_KEEP_COUNT_TEST)
        keep_count = int(po.override_hints.get('keep-count-test', common_constants.DEFAULT_KEEP_COUNT_TEST))
        for v in sorted(po.vermap.keys(), key=lambda v: SetupVersion(v), reverse=True):
            if 'test' in po.version_hints[v]:
                if keep_count <= 0:
                    break
                mark_package_fresh(packages, pn, v)
                keep_count = keep_count - 1

        # mark as fresh all versions after the first one which is newer than
        # the keep-days: override hint, (defaulting to DEFAULT_KEEP_DAYS)
        # (as opposed to checking the mtime for each version to determine if
        # it is included)
        keep_days = po.override_hints.get('keep-days', common_constants.DEFAULT_KEEP_DAYS)
        newer = False
        for v in sorted(po.vermap.keys(), key=lambda v: SetupVersion(v)):
            if not newer:
                if 'install' in po.vermap[v]:
                    if po.tar(v, 'install').mtime > (time.time() - (keep_days * 24 * 60 * 60)):
                        newer = True

            if newer:
                mark_package_fresh(packages, pn, v)

    # build a move list of stale versions
    stale = MoveList()
    for pn, po in packages.items():
        all_stale = {}

        for v in sorted(po.vermap.keys(), key=lambda v: SetupVersion(v)):
            all_stale[v] = True
            for category in ['source', 'install']:
                if category in po.vermap[v]:
                    if not getattr(po.tar(v, category), 'fresh', False):
                        to = po.tar(v, category)
                        stale.add(to.path, to.fn)
                        logging.debug("package '%s' version '%s' %s is stale" % (pn, v, category))
                    else:
                        all_stale[v] = False

        for v in po.hints:
            # if there's a pvr.hint without a fresh source or install of the
            # same version, move it as well
            if all_stale.get(v, True):
                stale.add(po.hints[v].path, po.hints[v].fn)
                logging.debug("package '%s' version '%s' hint is stale" % (pn, v))

        # clean up freshness mark
        for v in po.vermap:
            for c in ['source', 'install']:
                try:
                    delattr(po.tar(v, c), 'fresh')
                except (KeyError, AttributeError):
                    pass

    return stale


#
#
#

if __name__ == "__main__":
    for arch in common_constants.ARCHES:
        packages = read_packages(common_constants.FTP, arch)
        print("arch %s has %d packages" % (arch, len(packages)))

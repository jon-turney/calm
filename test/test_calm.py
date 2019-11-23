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
# tests
#

import collections
import contextlib
import filecmp
import io
import json
import logging
import os
import pprint
import re
import shutil
import tempfile
import types
import unittest

from calm.version import SetupVersion
import calm.calm
import calm.common_constants as common_constants
import calm.hint as hint
import calm.maintainers as maintainers
import calm.package as package
import calm.pkg2html as pkg2html
import calm.uploads as uploads


#
# helper functions
#
# write results to the file 'results'
# read expected from the file 'expected'
# compare them
#

def compare_with_expected_file(test, dirpath, results, basename=None):
    results_str = pprint.pformat(results, width=120)

    if basename:
        results_fn = basename + '.results'
        expected_fn = basename + '.expected'
    else:
        results_fn = 'results'
        expected_fn = 'expected'

    # save results in a file
    with open(os.path.join(dirpath, results_fn), 'w') as f:
        print(results_str, file=f)

    # read expected from a file
    with open(os.path.join(dirpath, expected_fn)) as f:
        expected = f.read().rstrip()

    test.assertMultiLineEqual(expected, results_str)


#
# capture a directory tree as a dict 'tree', where each key is a directory path
# and the value is a sorted list of filenames
#

def capture_dirtree(basedir):
    tree = {}
    for dirpath, _dirnames, filenames in os.walk(basedir):
        tree[os.path.relpath(dirpath, basedir)] = sorted(filenames)

    return tree


#
# a context to monkey-patch pprint so OrderedDict appears as with python <3.5
# (a dict, with lines ordered, rather than OrderedDict repr)
#

def patched_pprint_ordered_dict(self, obj, stream, indent, allowance, context, level):
    write = stream.write
    write('{')
    if self._indent_per_level > 1:
        write((self._indent_per_level - 1) * ' ')
    length = len(obj)
    if length:
        items = list(obj.items())
        self._format_dict_items(items, stream, indent, allowance + 1,
                                context, level)
    write('}')


@contextlib.contextmanager
def pprint_patch():
    if isinstance(getattr(pprint.PrettyPrinter, '_dispatch', None), dict):
        orig = pprint.PrettyPrinter._dispatch[collections.OrderedDict.__repr__]
        pprint.PrettyPrinter._dispatch[collections.OrderedDict.__repr__] = patched_pprint_ordered_dict
        try:
            yield
        finally:
            pprint.PrettyPrinter._dispatch[collections.OrderedDict.__repr__] = orig
    else:
        yield


#
#
#

class CalmTest(unittest.TestCase):
    def test_hint_parser(self):
        self.maxDiff = None

        basedir = 'testdata/relarea'
        for (dirpath, _subdirs, files) in os.walk(basedir):
            relpath = os.path.relpath(dirpath, basedir)
            for f in files:
                expected = os.path.join('testdata/hints', relpath)
                if f.endswith('.hint'):
                    if f == 'override.hint':
                        kind = hint.override
                        name = 'override'
                    elif f.endswith('-src.hint'):
                        kind = hint.spvr
                        name = f[:-5]
                    else:
                        kind = hint.pvr
                        name = f[:-5]
                    with self.subTest(package=os.path.basename(dirpath)):
                        logging.info('Reading %s' % os.path.join(dirpath, f))
                        results = hint.hint_file_parse(os.path.join(dirpath, f), kind)
                        with pprint_patch():
                            compare_with_expected_file(self, expected, results, name)

#
# something like "find -name results -exec sh -c 'cd `dirname {}` ; cp results
# expected' \;" can be used to update the expected output (after you have
# checked it to make sure it is really correct, of course :) )
#

    def test_html_writer(self):
        self.maxDiff = None

        htdocs = 'testdata/htdocs'
        args = types.SimpleNamespace()
        args.arch = 'x86'
        args.htdocs = htdocs
        args.rel_area = 'testdata/relarea'
        args.homedir = 'testdata/homes'
        args.dryrun = False
        args.force = True
        args.pkglist = 'testdata/pkglist/cygwin-pkg-maint'

        try:
            shutil.rmtree(htdocs)
        except FileNotFoundError:
            pass

        packages = {}
        for arch in common_constants.ARCHES:
            packages[arch] = {}
        packages[args.arch] = package.read_packages(args.rel_area, args.arch)
        package.validate_packages(args, packages[args.arch])
        pkg2html.update_package_listings(args, packages)

        # compare the output dirtree with expected
        with self.subTest('dirtree'):
            dirlist = capture_dirtree(htdocs)
            compare_with_expected_file(self, 'testdata/htdocs.expected', dirlist, 'dirtree')

        # compare the output files with expected
        for (dirpath, _subdirs, files) in os.walk(htdocs):
            relpath = os.path.relpath(dirpath, htdocs)
            for f in files:
                with self.subTest(file=os.path.join(relpath, f)):
                    results = os.path.join(htdocs, relpath, f)
                    expected = os.path.join('testdata/htdocs.expected', relpath, f)
                    if not filecmp.cmp(results, expected, shallow=False):
                        logging.info("%s different", os.path.join(relpath, f))
                        with open(results) as r, open(expected) as e:
                            self.assertMultiLineEqual(e.read(), r.read())
                    else:
                        logging.info("%s identical", os.path.join(relpath, f))

    def test_version_sort(self):
        test_data = [
            ["1.0.0", "2.0.0", -1],
            [".0.0", "2.0.0", -1],
            ["alpha", "beta", -1],
            ["1.0", "1.0.0", -1],
            ["2.456", "2.1000", -1],
            ["2.1000", "3.111", -1],
            ["2.001", "2.1", 0],
            ["2.34", "2.34", 0],
            ["6.1.2-4", "6.3.8-1", -1],
            ["1.7.3.0-2", "2.0.0-b8-1", -1],
            ["1.3.30c-2", "1.3.30c-10", -1],
            ["2.24.51-1", "2.25-1", -1],
            ["2.1.5+20120813+gitdcbe778-1", "2.1.5-3", 1],
            ["3.4.1-1", "3.4b1-1", 1],
            ["041206-1", "200090325-1", -1],
            ["0.6.2+git20130413-2", "0.6.2-1", 1],
            ["2.6.0+bzr6602-1", "2.6.0-2", 1],
            ["2.6.0-2", "2.6b2-1", 1],
            ["2.6.0+bzr6602-1", "2.6b2-1", 1],
            ["0.6.7+20150214+git3a710f9-1", "0.6.7-1", 1],
            ["15.8b-1", "15.8.0.1-2", -1],
            ["1.2rc1-1", "1.2.0-2", -1],
            ["20090325-1", "1:5.6.0-1", -1],
            ["0:20090325-1", "1:5.6.0-1", -1],
            ["2:20090325-1", "1:5.6.0-1", 1],
            ["2:1.0-1", "1:5.6.0-1", 1],
            ["1.0-1", "0:1.0-1", 0],
            # examples from https://fedoraproject.org/wiki/Archive:Tools/RPM/VersionComparison
            ["1.0010", "1.9", 1],
            ["1.05", "1.5", 0],
            ["1.0", "1", 1],
            ["2.50", "2.5", 1],
            ["fc4", "fc.4", 0],
            ["FC5", "fc4", -1],
            ["2a", "2.0", -1],
            ["1.0", "1.fc4", 1],
            ["3.0.0_fc", "3.0.0.fc", 0],
            # from RPM tests
            ["1.0", "1.0", 0],
            ["1.0", "2.0", -1],
            ["2.0", "1.0", 1],
            ["2.0.1", "2.0.1", 0],
            ["2.0", "2.0.1", -1],
            ["2.0.1", "2.0", 1],
            ["2.0.1a", "2.0.1a", 0],
            ["2.0.1a", "2.0.1", 1],
            ["2.0.1", "2.0.1a", -1],
            ["5.5p1", "5.5p1", 0],
            ["5.5p1", "5.5p2", -1],
            ["5.5p2", "5.5p1", 1],
            ["5.5p10", "5.5p10", 0],
            ["5.5p1", "5.5p10", -1],
            ["5.5p10", "5.5p1", 1],
            ["10xyz", "10.1xyz", -1],
            ["10.1xyz", "10xyz", 1],
            ["xyz10", "xyz10", 0],
            ["xyz10", "xyz10.1", -1],
            ["xyz10.1", "xyz10", 1],
            ["xyz.4", "xyz.4", 0],
            ["xyz.4", "8", -1],
            ["8", "xyz.4", 1],
            ["xyz.4", "2", -1],
            ["2", "xyz.4", 1],
            ["5.5p2", "5.6p1", -1],
            ["5.6p1", "5.5p2", 1],
            ["5.6p1", "6.5p1", -1],
            ["6.5p1", "5.6p1", 1],
            ["6.0.rc1", "6.0", 1],
            ["6.0", "6.0.rc1", -1],
            ["10b2", "10a1", 1],
            ["10a2", "10b2", -1],
            ["1.0aa", "1.0aa", 0],
            ["1.0a", "1.0aa", -1],
            ["1.0aa", "1.0a", 1],
            ["10.0001", "10.0001", 0],
            ["10.0001", "10.1", 0],
            ["10.1", "10.0001", 0],
            ["10.0001", "10.0039", -1],
            ["10.0039", "10.0001", 1],
            ["4.999.9", "5.0", -1],
            ["5.0", "4.999.9", 1],
            ["20101121", "20101121", 0],
            ["20101121", "20101122", -1],
            ["20101122", "20101121", 1],
            ["2_0", "2_0", 0],
            ["2.0", "2_0", 0],
            ["2_0", "2.0", 0],
            ["a", "a", 0],
            ["a+", "a+", 0],
            ["a+", "a_", 0],
            ["a_", "a+", 0],
            ["+a", "+a", 0],
            ["+a", "_a", 0],
            ["_a", "+a", 0],
            ["+_", "+_", 0],
            ["_+", "+_", 0],
            ["_+", "_+", 0],
            ["+", "_", 0],
            ["_", "+", 0],
        ]

        for d in test_data:
            a = SetupVersion(d[0])
            b = SetupVersion(d[1])
            e = d[2]
            # logging.info("%s %s %d" % (a, b, e))
            self.assertEqual(SetupVersion.__cmp__(a, b), e, msg='%s %s %d' % (a, b, e))
            self.assertEqual(SetupVersion.__cmp__(b, a), -e, msg='%s %s %d' % (a, b, -e))

    def test_maint_pkglist(self):
        self.maxDiff = None

        mlist = {}
        mlist = maintainers.add_directories(mlist, 'testdata/homes')
        mlist = maintainers.add_packages(mlist, 'testdata/pkglist/cygwin-pkg-maint', None)

        compare_with_expected_file(self, 'testdata/pkglist', mlist)

    def test_scan_uploads(self):
        self.maxDiff = None

        test_root = tempfile.mktemp()
        logging.info('test_root = %s', test_root)

        args = types.SimpleNamespace()
        args.arch = 'x86'
        args.rel_area = 'testdata/relarea'
        args.dryrun = False

        shutil.copytree('testdata/homes', os.path.join(test_root, 'testdata/homes'))
        oldcwd = os.getcwd()
        os.chdir(test_root)

        pkglist = ['after-ready', 'not-ready', 'testpackage', 'testpackage2', 'testpackage-zstd']

        mlist = {}
        mlist = maintainers.add_directories(mlist, 'testdata/homes')
        m = mlist['Blooey McFooey']
        m.pkgs.extend(pkglist + ['not-on-package-list'])

        ready_fns = [(os.path.join(m.homedir(), 'x86', 'release', 'testpackage', '!ready'), ''),
                     (os.path.join(m.homedir(), 'x86', 'release', 'testpackage2', 'testpackage2-subpackage', '!ready'), ''),
                     (os.path.join(m.homedir(), 'x86', 'release', 'testpackage-zstd', '!ready'), ''),
                     (os.path.join(m.homedir(), 'x86', 'release', 'after-ready', '!ready'), '-t 198709011700'),
                     (os.path.join(m.homedir(), 'x86', 'release', 'corrupt', '!ready'), '')]
        for (f, t) in ready_fns:
            os.system('touch %s "%s"' % (t, f))

        scan_result = uploads.scan(m, pkglist + ['not-on-maintainer-list'], args.arch, args)

        os.chdir(oldcwd)
        shutil.rmtree(test_root)

        self.assertEqual(scan_result.error, False)
        compare_with_expected_file(self, 'testdata/uploads', dict(scan_result.to_relarea.movelist), 'move')
        self.assertCountEqual(scan_result.to_vault.movelist, {'x86/release/testpackage': ['x86/release/testpackage/testpackage-0.1-1.tar.bz2']})
        self.assertCountEqual(scan_result.remove_always, [f for (f, t) in ready_fns])
        self.assertEqual(scan_result.remove_success, ['testdata/homes/Blooey McFooey/x86/release/testpackage/-testpackage-0.1-1-src.tar.bz2', 'testdata/homes/Blooey McFooey/x86/release/testpackage/-testpackage-0.1-1.tar.bz2'])
        with pprint_patch():
            compare_with_expected_file(self, 'testdata/uploads', dict(scan_result.packages), 'pkglist')

    def test_package_set(self):
        self.maxDiff = None

        args = types.SimpleNamespace()
        args.arch = 'x86'
        args.dryrun = False
        args.force = True
        args.inifile = 'testdata/inifile/setup.ini'
        args.pkglist = 'testdata/pkglist/cygwin-pkg-maint'
        args.rel_area = 'testdata/relarea'
        args.release = 'testing'
        args.setup_version = '4.321'

        packages = package.read_packages(args.rel_area, args.arch)
        package.delete(packages, 'x86/release/nonexistent', 'nosuchfile-1.0.0.tar.xz')
        self.assertEqual(package.validate_packages(args, packages), True)
        package.write_setup_ini(args, packages, args.arch)
        with open(args.inifile) as inifile:
            results = inifile.read()
            # fix the timestamp to match expected
            results = re.sub('setup-timestamp: .*', 'setup-timestamp: 1458221800', results, 1)
            results = re.sub('generated at .*', 'generated at 2016-03-17 13:36:40 GMT', results, 1)
            compare_with_expected_file(self, 'testdata/inifile', (results,), 'setup.ini')

        # XXX: delete a needed package, and check validate fails

    def test_process_uploads_conflict(self):
        self.maxDiff = None

        args = types.SimpleNamespace()

        for d in ['rel_area', 'homedir', 'htdocs', 'vault']:
            setattr(args, d, tempfile.mktemp())
            logging.info('%s = %s', d, getattr(args, d))

        shutil.copytree('testdata/relarea', args.rel_area)
        shutil.copytree('testdata/homes.conflict', args.homedir)

        args.dryrun = False
        args.email = None
        args.force = False
        args.pkglist = 'testdata/pkglist/cygwin-pkg-maint'
        args.stale = True

        # set appropriate !ready
        m_homedir = os.path.join(args.homedir, 'Blooey McFooey')
        os.system('touch "%s"' % (os.path.join(m_homedir, 'x86', 'release', 'staleversion', '!ready')))

        state = calm.calm.CalmState()
        state.packages = calm.calm.process_relarea(args, state)
        state.packages = calm.calm.process_uploads(args, state)
        self.assertTrue(state.packages)

        for d in ['rel_area', 'homedir', 'htdocs', 'vault']:
            with self.subTest(directory=d):
                dirlist = capture_dirtree(getattr(args, d))
                compare_with_expected_file(self, 'testdata/conflict', dirlist, d)
                shutil.rmtree(getattr(args, d))

    def test_process(self):
        self.maxDiff = None

        args = types.SimpleNamespace()

        for d in ['rel_area', 'homedir', 'htdocs', 'vault']:
            setattr(args, d, tempfile.mktemp())
            logging.info('%s = %s', d, getattr(args, d))

        args.dryrun = False
        args.email = None
        args.force = False
        args.inifile = os.path.join(args.rel_area, 'setup.ini')
        args.pkglist = 'testdata/pkglist/cygwin-pkg-maint'
        args.release = 'trial'
        args.setup_version = '3.1415'
        args.stale = True

        state = calm.calm.CalmState()

        shutil.copytree('testdata/relarea', args.rel_area)
        shutil.copytree('testdata/homes', args.homedir)

        # set appropriate !readys
        m_homedir = os.path.join(args.homedir, 'Blooey McFooey')
        ready_fns = [(os.path.join(m_homedir, 'x86', 'release', 'testpackage', '!ready'), ''),
                     (os.path.join(m_homedir, 'x86', 'release', 'testpackage2', 'testpackage2-subpackage', '!ready'), ''),
                     (os.path.join(m_homedir, 'x86', 'release', 'after-ready', '!ready'), '-t 198709011700'),
                     (os.path.join(m_homedir, 'noarch', 'release', 'perl-Net-SMTP-SSL', '!ready'), ''),
                     (os.path.join(m_homedir, 'x86', 'release', 'corrupt', '!ready'), ''),
                     (os.path.join(m_homedir, 'x86', 'release', 'per-version', '!ready'), ''),
                     (os.path.join(m_homedir, 'x86', 'release', 'per-version-replacement-hint-only', '!ready'), '')]
        for (f, t) in ready_fns:
            os.system('touch %s "%s"' % (t, f))

        packages = calm.calm.process(args, state)
        self.assertTrue(packages)

        pkg2html.update_package_listings(args, packages)
        package.write_setup_ini(args, packages['x86'], 'x86')

        with open(os.path.join(args.rel_area, 'setup.ini')) as inifile:
            results = inifile.read()
            # fix the timestamp to match expected
            results = re.sub('setup-timestamp: .*', 'setup-timestamp: 1473797080', results, 1)
            results = re.sub('generated at .*', 'generated at 2016-09-13 21:04:40 BST', results, 1)
            compare_with_expected_file(self, 'testdata/process_arch', (results,), 'setup.ini')

        for d in ['rel_area', 'homedir', 'htdocs', 'vault']:
            with self.subTest(directory=d):
                dirlist = capture_dirtree(getattr(args, d))
                compare_with_expected_file(self, 'testdata/process_arch', dirlist, d)

        with io.StringIO() as jsonfile:
            package.write_repo_json(args, packages, jsonfile)
            j = json.loads(jsonfile.getvalue(), object_pairs_hook=collections.OrderedDict)
            del j['timestamp']
            compare_with_expected_file(self, 'testdata/process_arch', json.dumps(j, sort_keys=True, indent=4), 'packages.json')

        for d in ['rel_area', 'homedir', 'htdocs', 'vault']:
            shutil.rmtree(getattr(args, d))

    @classmethod
    def setUpClass(cls):
        # testdata is located in the same directory as this file
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

        # ensure sha512.sum files exist
        os.system("find testdata/relarea/x86 testdata/relarea/noarch -type d -exec sh -c 'cd {} ; sha512sum * >sha512.sum 2>/dev/null' \\;")
        # should remove a sha512.sum file so that we test functioning when it's absent
        os.unlink('testdata/relarea/x86/release/arc/sha512.sum')
        # remove !ready files
        os.system("find testdata/homes -name !ready -exec rm {} \\;")

        # fix up package timestamps
        # (git doesn't store timestamps, so they will all be dated the time of checkout)

        # set all package timestamps to some arbitrary date
        os.environ['TZ'] = 'UTC'
        for dirpath, _dirnames, filenames in os.walk(os.path.join('testdata', 'relarea')):
            for f in filenames:
                os.system('touch "%s" -d %s' % (os.path.join(dirpath, f), '2018-03-02'))

        # then adjust packages where we need highest version to also be latest
        relarea_x86 = os.path.join('testdata', 'relarea', 'x86', 'release')
        relarea_noarch = os.path.join('testdata', 'relarea', 'noarch', 'release')
        home_conflict = os.path.join('testdata', 'homes.conflict', 'Blooey McFooey', 'x86', 'release')
        touches = [(os.path.join(relarea_x86, 'cygwin', 'cygwin-2.2.0-1.tar.xz'), '2016-11-01'),
                   (os.path.join(relarea_x86, 'cygwin', 'cygwin-2.2.0-1-src.tar.xz'), '2016-11-01'),
                   (os.path.join(relarea_x86, 'cygwin', 'cygwin-2.2.1-1.tar.xz'), '2016-11-02'),
                   (os.path.join(relarea_x86, 'cygwin', 'cygwin-2.2.1-1-src.tar.xz'), '2016-11-02'),
                   (os.path.join(relarea_x86, 'cygwin', 'cygwin-debuginfo', 'cygwin-debuginfo-2.2.0-1.tar.xz'), '2016-11-01'),
                   (os.path.join(relarea_x86, 'cygwin', 'cygwin-debuginfo', 'cygwin-debuginfo-2.2.1-1.tar.xz'), '2016-11-02'),
                   (os.path.join(relarea_x86, 'cygwin', 'cygwin-devel', 'cygwin-devel-2.2.0-1.tar.xz'), '2016-11-01'),
                   (os.path.join(relarea_x86, 'cygwin', 'cygwin-devel', 'cygwin-devel-2.2.1-1.tar.xz'), '2016-11-02'),
                   (os.path.join(relarea_x86, 'base-cygwin', 'base-cygwin-3.6-1.tar.xz'), '2016-11-02'),
                   (os.path.join(relarea_x86, 'per-version', 'per-version-4.0-1.tar.xz'), '2017-04-09'),
                   (os.path.join(relarea_x86, 'per-version', 'per-version-4.0-1-src.tar.xz'), '2017-04-09'),
                   (os.path.join(relarea_x86, 'rpm-doc', 'rpm-doc-4.1-2.tar.bz2'), '2016-11-02'),
                   (os.path.join(relarea_x86, 'rpm-doc', 'rpm-doc-4.1-2-src.tar.bz2'), '2016-11-02'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-240-1.tar.xz'), '2017-04-07'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-240-1-src.tar.xz'), '2017-04-07'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-242-0.tar.xz'), '2017-04-08'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-242-0-src.tar.xz'), '2017-04-08'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-243-0.tar.xz'), '2017-04-09'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-243-0-src.tar.xz'), '2017-04-09'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-250-0.tar.xz'), '2017-04-10'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-250-0-src.tar.xz'), '2017-04-10'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-251-0.tar.xz'), '2017-04-09'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-251-0-src.tar.xz'), '2017-04-09'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-260-0.tar.xz'), '2017-04-12'),
                   (os.path.join(relarea_x86, 'staleversion', 'staleversion-260-0-src.tar.xz'), '2017-04-12'),
                   (os.path.join(relarea_x86, 'keychain', 'keychain-2.6.8-1.tar.bz2'), '2016-11-02'),
                   (os.path.join(relarea_x86, 'keychain', 'keychain-2.6.8-1-src.tar.bz2'), '2016-11-02'),
                   (os.path.join(relarea_noarch, 'perl-Net-SMTP-SSL', 'perl-Net-SMTP-SSL-1.01-1.tar.xz'), '2016-09-01'),
                   (os.path.join(relarea_noarch, 'perl-Net-SMTP-SSL', 'perl-Net-SMTP-SSL-1.01-1-src.tar.xz'), '2016-09-01'),
                   (os.path.join(relarea_noarch, 'perl-Net-SMTP-SSL', 'perl-Net-SMTP-SSL-1.02-1.tar.xz'), '2016-10-01'),
                   (os.path.join(relarea_noarch, 'perl-Net-SMTP-SSL', 'perl-Net-SMTP-SSL-1.02-1-src.tar.xz'), '2016-10-01'),
                   (os.path.join(relarea_noarch, 'perl-Net-SMTP-SSL', 'perl-Net-SMTP-SSL-1.03-1.tar.xz'), '2016-11-01'),
                   (os.path.join(relarea_noarch, 'perl-Net-SMTP-SSL', 'perl-Net-SMTP-SSL-1.03-1-src.tar.xz'), '2016-11-01'),
                   (os.path.join(home_conflict, 'staleversion', 'staleversion-230-1.hint'), '2017-04-06'),
                   (os.path.join(home_conflict, 'staleversion', 'staleversion-230-1.tar.xz'), '2017-04-06'),
                   (os.path.join(home_conflict, 'staleversion', 'staleversion-230-1-src.tar.xz'), '2017-04-06')]
        for (f, t) in touches:
            os.system('touch "%s" -d %s' % (f, t))

        # ensure !reminder-timestamp is created for uploads
        home = os.path.join('testdata', 'homes', 'Blooey McFooey')
        os.system('find "%s" -type f -exec touch -d "12 hours ago" {} +' % (home))


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format='%(message)s')
    unittest.main()

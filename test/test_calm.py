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

import filecmp
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
    for dirpath, dirnames, filenames in os.walk(basedir):
        tree[os.path.relpath(dirpath, basedir)] = sorted(filenames)

    return tree


#
#
#

class CalmTest(unittest.TestCase):
    def test_hint_parser(self):
        self.maxDiff = None

        basedir = 'testdata/relarea'
        for (dirpath, subdirs, files) in os.walk(basedir):
            relpath = os.path.relpath(dirpath, basedir)
            if 'setup.hint' in files:
                with self.subTest(package=os.path.basename(dirpath)):
                    logging.info('Reading %s' % os.path.join(dirpath, 'setup.hint'))
                    results = hint.hint_file_parse(os.path.join(dirpath, 'setup.hint'), hint.setup)
                    compare_with_expected_file(self, os.path.join('testdata/hints', relpath), results)

#
# something like "find -name results -exec sh -c 'cd `dirname {}` ; cp results
# expected' \;" can be used to update the expected output (after you have
# checking it to make sure it is really correct, of course :) )
#

    def test_html_writer(self):
        self.maxDiff = None

        htdocs = 'testdata/htdocs'
        args = types.SimpleNamespace()
        setattr(args, 'arch', 'x86')
        setattr(args, 'htdocs', htdocs)
        setattr(args, 'rel_area', 'testdata/relarea')
        setattr(args, 'dryrun', False)
        setattr(args, 'force', True)
        setattr(args, 'pkglist', 'testdata/pkglist/cygwin-pkg-maint')

        packages = package.read_packages(args.rel_area, args.arch)
        package.validate_packages(args, packages)
        pkg2html.update_package_listings(args, packages, args.arch)

        # compare the output files with expected
        for (dirpath, subdirs, files) in os.walk(htdocs):
            relpath = os.path.relpath(dirpath, htdocs)
            for f in files:
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
            ["1.2rc1-1","1.2.0-2", -1],
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
        mlist = maintainers.Maintainer.add_directories(mlist, 'testdata/homes')
        mlist = maintainers.Maintainer.add_packages(mlist, 'testdata/pkglist/cygwin-pkg-maint', None)

        compare_with_expected_file(self, 'testdata/pkglist', mlist)

    def test_scan_uploads(self):
        self.maxDiff = None

        args = types.SimpleNamespace()
        setattr(args, 'arch', 'x86')
        setattr(args, 'rel_area', 'testdata/relarea')
        setattr(args, 'dryrun', False)

        pkglist = ['after-ready', 'not-ready', 'testpackage', 'testpackage2']

        mlist = {}
        mlist = maintainers.Maintainer.add_directories(mlist, 'testdata/homes')
        m = mlist['Blooey McFooey']
        m.pkgs.extend(pkglist + ['not-on-package-list'])

        ready_fns = [(os.path.join(m.homedir(), 'x86', 'release', 'testpackage', '!ready'), ''),
                     (os.path.join(m.homedir(), 'x86', 'release', 'testpackage2', 'testpackage2-subpackage', '!ready'), ''),
                     (os.path.join(m.homedir(), 'x86', 'release', 'after-ready', '!ready'), '-t 198709011700'),
                     (os.path.join(m.homedir(), 'x86', 'release', 'corrupt', '!ready'), '')]
        for (f, t) in ready_fns:
            os.system('touch %s "%s"' % (t, f))

        scan_result = uploads.scan(m, pkglist + ['not-on-maintainer-list'], args.arch, args)

        self.assertEqual(scan_result.error, False)
        compare_with_expected_file(self, 'testdata/uploads', scan_result.to_relarea, 'move')
        self.assertCountEqual(scan_result.to_vault, {'x86/release/testpackage': ['x86/release/testpackage/testpackage-0.1-1.tar.bz2']})
        self.assertCountEqual(scan_result.remove_always, [f for (f, t) in ready_fns])
        self.assertEqual(scan_result.remove_success, ['testdata/homes/Blooey McFooey/x86/release/testpackage/-testpackage-0.1-1-src.tar.bz2', 'testdata/homes/Blooey McFooey/x86/release/testpackage/-testpackage-0.1-1.tar.bz2'])
        compare_with_expected_file(self, 'testdata/uploads', scan_result.packages, 'pkglist')

    def test_package_set(self):
        self.maxDiff = None

        args = types.SimpleNamespace()
        setattr(args, 'arch', 'x86')
        setattr(args, 'dryrun', False)
        setattr(args, 'force', True)
        setattr(args, 'inifile', 'testdata/inifile/setup.ini')
        setattr(args, 'pkglist', 'testdata/pkglist/cygwin-pkg-maint')
        setattr(args, 'rel_area', 'testdata/relarea')
        setattr(args, 'release', 'testing')
        setattr(args, 'setup_version', '4.321')

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

    def test_process(self):
        self.maxDiff = None

        args = types.SimpleNamespace()

        for d in ['rel_area', 'homedir', 'htdocs', 'vault']:
            setattr(args, d, tempfile.mktemp())
            logging.info('%s = %s', d, getattr(args, d))

        setattr(args, 'dryrun', False)
        setattr(args, 'email', None)
        setattr(args, 'force', False)
        setattr(args, 'inifile', os.path.join(getattr(args, 'rel_area'), 'setup.ini'))
        setattr(args, 'pkglist', 'testdata/pkglist/cygwin-pkg-maint')
        setattr(args, 'release', 'trial')
        setattr(args, 'setup_version', '3.1415')
        setattr(args, 'stale', True)

        state = calm.calm.CalmState()

        shutil.copytree('testdata/relarea', getattr(args, 'rel_area'))
        shutil.copytree('testdata/homes', getattr(args, 'homedir'))

        # set appropriate !readys
        m_homedir = os.path.join(getattr(args, 'homedir'), 'Blooey McFooey')
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

        pkg2html.update_package_listings(args, packages['x86'], 'x86')
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
                shutil.rmtree(getattr(args, d))

    @classmethod
    def setUpClass(cls):
        # testdata is located in the same directory as this file
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

        # ensure sha512.sum files exist
        os.system("find testdata/relarea/x86 testdata/relarea/noarch -type d -exec sh -c 'cd {} ; sha512sum * >sha512.sum 2>/dev/null' \;")
        # should remove a sha512.sum file so that we test functioning when it's absent
        os.unlink('testdata/relarea/x86/release/arc/sha512.sum')
        # remove !ready files
        os.system("find testdata/homes -name !ready -exec rm {} \;")


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format='%(message)s')
    unittest.main()

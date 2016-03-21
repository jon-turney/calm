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

from version import SetupVersion
import calm
import hint
import maintainers
import package
import pkg2html
import uploads


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

class TestMain(unittest.TestCase):
    def test_hint_parser(self):
        self.maxDiff = None

        basedir = 'testdata/x86/release'
        for (dirpath, subdirs, files) in os.walk(basedir):
            relpath = os.path.relpath(dirpath, basedir)
            if 'setup.hint' in files:
                with self.subTest(package=os.path.basename(dirpath)):
                    logging.info('Reading %s' % os.path.join(dirpath, 'setup.hint'))
                    results = hint.setup_hint_parse(os.path.join(dirpath, 'setup.hint'))
                    compare_with_expected_file(self, os.path.join('testdata/x86.hints/release', relpath), results)

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
        setattr(args, 'rel_area', 'testdata')
        setattr(args, 'dryrun', False)
        setattr(args, 'force', True)
        setattr(args, 'pkglist', 'testdata/pkglist/cygwin-pkg-maint')

        packages = package.read_packages(args.rel_area, args.arch)
        package.validate_packages(args, packages)
        pkg2html.update_package_listings(args, packages)

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
            ["3.4.1-1", "3.4b1-1", -1],
            ["041206-1", "200090325-1", -1],
            ["0.6.2+git20130413-2", "0.6.2-1", 1],
            ["2.6.0+bzr6602-1", "2.6.0-2", 1],
            ["2.6.0-2", "2.6b2-1", -1],
            ["2.6.0+bzr6602-1", "2.6b2-1", -1],
            ["0.6.7+20150214+git3a710f9-1", "0.6.7-1", 1],
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
        setattr(args, 'rel_area', 'testdata')
        setattr(args, 'dryrun', False)

        pkglist = ['after-ready', 'not-ready', 'testpackage', 'testpackage2']

        mlist = {}
        mlist = maintainers.Maintainer.add_directories(mlist, 'testdata/homes')
        m = mlist['Blooey McFooey']
        m.pkgs.extend(pkglist + ['not-on-package-list'])

        ready_fns = [(os.path.join(m.homedir(), 'x86', 'release', 'testpackage', '!ready'), ''),
                     (os.path.join(m.homedir(), 'x86', 'release', 'testpackage2', 'testpackage2-subpackage', '!ready'), ''),
                     (os.path.join(m.homedir(), 'x86', 'release', 'after-ready', '!ready'), '-t 198709011700')]
        for (f, t) in ready_fns:
            os.system('touch %s "%s"' % (t, f))

        (error, packages, to_relarea, to_vault, remove_always, remove_success) = uploads.scan(m, pkglist + ['not-on-maintainer-list'], args)

        self.assertEqual(error, False)
        compare_with_expected_file(self, 'testdata/uploads', to_relarea, 'move')
        self.assertCountEqual(remove_always, [f for (f, t) in ready_fns])
        self.assertEqual(remove_success, ['testdata/homes/Blooey McFooey/x86/release/testpackage/-testpackage-0.1-1.tar.bz2'])
        compare_with_expected_file(self, 'testdata/uploads', packages, 'pkglist')

    def test_package_set(self):
        self.maxDiff = None

        args = types.SimpleNamespace()
        setattr(args, 'arch', 'x86')
        setattr(args, 'dryrun', False)
        setattr(args, 'force', True)
        setattr(args, 'inifile', 'testdata/inifile/setup.ini')
        setattr(args, 'pkglist', 'testdata/pkglist/cygwin-pkg-maint')
        setattr(args, 'rel_area', 'testdata')
        setattr(args, 'release', 'testing')
        setattr(args, 'setup_version', '4.321')

        packages = package.read_packages(args.rel_area, args.arch)
        package.delete(packages, 'release/nonexistent', 'nosuchfile-1.0.0.tar.xz')
        self.assertEqual(package.validate_packages(args, packages), True)
        package.write_setup_ini(args, packages)
        with open(args.inifile) as inifile:
            results = inifile.read()
            # fix the timestamp to match expected
            results = re.sub('setup-timestamp: .*', 'setup-timestamp: 1458221800', results, 1)
            compare_with_expected_file(self, 'testdata/inifile', (results,), 'setup.ini')

        # XXX: delete a needed package, and check validate fails

    def test_process_arch(self):
        self.maxDiff = None

        args = types.SimpleNamespace()

        for d in ['rel_area', 'homedir', 'htdocs', 'vault']:
            setattr(args, d, tempfile.mktemp())
            logging.info('%s = %s', d, getattr(args, d))

        setattr(args, 'arch', 'x86')
        setattr(args, 'dryrun', False)
        setattr(args, 'email', None)
        setattr(args, 'force', False)
        setattr(args, 'inifile', os.path.join(getattr(args, 'rel_area'), 'setup.ini'))
        setattr(args, 'pkglist', 'testdata/pkglist/cygwin-pkg-maint')
        setattr(args, 'release', 'trial')
        setattr(args, 'setup_version', '3.1415')

        shutil.copytree('testdata/x86', os.path.join(getattr(args, 'rel_area'), 'x86'))
        shutil.copytree('testdata/homes', getattr(args, 'homedir'))

        # set appropriate !readys
        m_homedir = os.path.join(getattr(args, 'homedir'), 'Blooey McFooey')
        ready_fns = [(os.path.join(m_homedir, 'x86', 'release', 'testpackage', '!ready'), ''),
                     (os.path.join(m_homedir, 'x86', 'release', 'testpackage2', 'testpackage2-subpackage', '!ready'), ''),
                     (os.path.join(m_homedir, 'x86', 'release', 'after-ready', '!ready'), '-t 198709011700')]
        for (f, t) in ready_fns:
            os.system('touch %s "%s"' % (t, f))

        self.assertEqual(calm.process_arch(args), True)

        for d in ['rel_area', 'homedir', 'htdocs', 'vault']:
            with self.subTest(directory=d):
                dirlist = capture_dirtree(getattr(args, d))
                compare_with_expected_file(self, 'testdata/process_arch', dirlist, d)
                shutil.rmtree(getattr(args, d))

if __name__ == '__main__':
    # ensure sha512.sum files exist
    os.system("find testdata/x86 -type d -exec sh -c 'cd {} ; sha512sum * >sha512.sum 2>/dev/null' \;")
    # should remove a sha512.sum file so that we test functioning when it's absent
    os.unlink('testdata/x86/release/naim/sha512.sum')
    # remove !ready files
    os.system("find testdata/homes -name !ready -exec rm {} \;")

    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format='%(message)s')
    unittest.main()

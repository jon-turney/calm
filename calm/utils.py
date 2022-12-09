#!/usr/bin/env python3
#
# Copyright (c) 2019 Jon Turney
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
# utility functions
#

import filecmp
import logging
import os
import subprocess
from contextlib import contextmanager


#
# touch a file
#
def touch(fn, times=None):
    try:
        with open(fn, 'a'):  # ensure fn exists
            os.utime(fn, times)
    except PermissionError:
        logging.error("couldn't update mtime for %s" % (fn))


#
# ensure a directory exists
#
# for some versions of python, os.makedirs() can still raise FileExistsError
# even when exists_ok=True, if the directory mode is not as expected.
#
def makedirs(name):
    try:
        os.makedirs(name, exist_ok=True)
    except FileExistsError:
        pass


#
# remove any empty subdirectories below a given depth
#
def rmemptysubdirs(path, depth=3):
    for (dirpath, _subdirs, _files) in os.walk(path, topdown=False, followlinks=True):
        # don't do anything while above the given depth
        if len(os.path.relpath(dirpath, path).split(os.sep)) < depth:
            continue

        # check whether the directory is now empty after processing any
        # subdirectories, and if so, remove it
        if len(os.listdir(dirpath)) == 0:
            logging.debug('rmdir %s' % dirpath)
            os.rmdir(dirpath)


#
# a wrapper for open() which:
#
# - atomically changes the file contents (atomic)
# - only touches the mtime if the file contents have changed (move-if-changed)
#
@contextmanager
def open_amifc(filepath, mode='w', cb=None):
    tmppath = filepath + '~'
    while os.path.isfile(tmppath):
        tmppath += '~'

    try:
        with open(tmppath, mode) as file:
            logging.debug('writing %s for move-if-changed' % (tmppath))
            yield file

        changed = not os.path.exists(filepath) or not filecmp.cmp(tmppath, filepath, shallow=False)
        if changed:
            logging.info("writing %s" % (filepath))
            os.rename(tmppath, filepath)
        else:
            logging.debug("unchanged %s" % (filepath))
    finally:
        try:
            os.remove(tmppath)
        except OSError:
            pass

    # notify callback if file was changed or not
    if cb:
        cb(changed)


#
# run a subprocess, logging it's output
#
# N.B. because we use shell=True, args should be a string to be supplied to 'sh
# -c', not a list.
#
def system(args):
    logging.debug(args)
    try:
        output = subprocess.check_output(args, shell=True,
                                         stdin=subprocess.DEVNULL,
                                         stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        for l in e.output.decode().splitlines():
            logging.warning(l)
        logging.warning('%s exited %d' % (args.split()[0], e.returncode))
    else:
        for l in output.decode().splitlines():
            logging.info(l)


#
# This provides a simple wrapper around a function which takes a pathname as
# it's only parameter.  The result is cached as long as the mtime of the
# pathname is unchanged.
#
def mtime_cache(user_function):
    sentinel = object()          # unique object used to signal cache misses
    cache = {}

    def wrapper(key):
        # make sure path is absolute
        key = os.path.abspath(key)

        (result, mtime) = cache.get(key, (sentinel, 0))

        new_mtime = os.path.getmtime(key)

        # cache hit
        if result is not sentinel:
            # cache valid
            if new_mtime == mtime:
                return result
            else:
                logging.debug('%s cache invalidated by mtime change' % key)

        # cache miss
        result = user_function(key)
        cache[key] = (result, new_mtime)
        return result

    return wrapper

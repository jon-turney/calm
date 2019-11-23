#!/usr/bin/env python3
#
# Copyright (c) 2022 Jon Turney
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
# package db
#


import logging
import os
import sqlite3

from . import utils


def connect(args):
    utils.makedirs(args.htdocs)
    dbfn = os.path.join(args.htdocs, 'calm.db')
    logging.debug("sqlite3 database %s" % (dbfn))

    conn = sqlite3.connect(dbfn, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute('''CREATE TABLE IF NOT EXISTS historic_package_names
                    (name TEXT NOT NULL PRIMARY KEY
                    )''')
    conn.commit()

    return conn


#
# this tracks the set of all names we have ever had for packages, and returns
# ones which aren't in the set of names for current package
#
def update_package_names(args, packages):
    current_names = set()
    for arch in packages:
        current_names.update(packages[arch])

    with connect(args) as conn:
        conn.row_factory = sqlite3.Row

        cur = conn.execute("SELECT name FROM historic_package_names")
        historic_names = set([row['name'] for row in cur.fetchall()])

        # add newly appearing names to current_names
        for n in (current_names - historic_names):
            conn.execute('INSERT INTO historic_package_names (name) VALUES (?)', (n,))
            logging.debug("package '%s' name is added" % (n))

    # this is data isn't quite perfect for this purpose: it doesn't know about:
    # - names which the removed package provide:d
    # - other packages which might provide: the name of a removed package
    return (historic_names - current_names)

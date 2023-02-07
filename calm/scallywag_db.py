#!/usr/bin/env python3
#
# Copyright (c) 2023 Jon Turney
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

import contextlib
import os
import sqlite3
from collections import namedtuple

basedir = os.path.dirname(os.path.realpath(__file__))
dbfile = os.path.join(basedir, '..', '..', 'scallywag', 'carpetbag.db')


def namedtuple_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    row_cls = namedtuple("row_cls", fields)
    return row_cls(*row)


def do_deploys(cb):
    if not os.path.exists(dbfile):
        return

    with contextlib.closing(sqlite3.connect(dbfile)) as conn:
        conn.row_factory = namedtuple_factory

        cur = conn.execute("SELECT * FROM jobs WHERE status = 'deploying'")
        rows = cur.fetchall()

        for r in rows:
            status = 'deploy succeeded'
            if not cb(r):
                status = 'deploy failed'

            conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, r.id))

        conn.commit()

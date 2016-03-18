#!/usr/bin/env python3
#
# Tell irked to send a message to an IRC channel
#
# First argument must be a channel URL. If it does not begin with "irc",
# the base URL for freenode is prepended.
#
# SPDX-License-Identifier: BSD-2-Clause

import json
import socket
import sys

DEFAULT_SERVER = ("localhost", 6659)


def connect(server=DEFAULT_SERVER):
    return socket.create_connection(server)


def send(s, target, message):
    data = {"to": target, "privmsg": message}
    # print(json.dumps(data))
    s.sendall(bytes(json.dumps(data), "ascii"))


def irk(message, target='cygwin-developers', server=DEFAULT_SERVER):
    s = connect(server)
    if "irc:" not in target and "ircs:" not in target:
        target = "irc://chat.freenode.net/{0}".format(target)

    send(s, target, message)

    s.close()


def main():
    message = " ".join(sys.argv[:])

    try:
        irk(message)
    except socket.error as e:
        sys.stderr.write("irk: write to server failed: %r\n" % e)
        sys.exit(1)

if __name__ == '__main__':
    main()

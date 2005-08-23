#!/usr/bin/env python
#
# A plugin for the Yellowdog Updater Modified which sorts each repo's
# mirrorlist by connection speed prior to downloading packages.
#
# Configuration Options
# /etc/yum/pluginconf.d/fastestmirror.conf:
#   [main]
#   enabled=1
#   verbose=1
#   timeout=3
#   stop_after=2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# (C) Copyright 2005 Luke Macken <lmacken@redhat.com>

import sys
import time
import socket
import urlparse
import asyncore

from yum.plugins import TYPE_INTERFACE, TYPE_CORE

requires_api_version = '2.1'
plugin_type = (TYPE_INTERFACE, TYPE_CORE)

verbose = False
timeout = 3
stop_after = 2

def init_hook(conduit):
    global verbose, timeout
    verbose = conduit.confBool('main', 'verbose', default=False)
    timeout = conduit.confInt('main', 'timeout', default=3)
    stop_after = conduit.confString('main', 'stop_after', default=2)

def predownload_hook(conduit):
    repomirrors = {}
    conduit.info(2, "Determining fastest mirrors")
    for pkg in conduit.getDownloadPackages():
        repo = conduit.getRepos().getRepo(pkg.repoid)
        if not repomirrors.has_key(str(repo)):
            repomirrors[str(repo)] = FastestMirror(repo.urls).get_mirrorlist()
        repo.set('urls', repomirrors[str(repo)])
        repo.set('failovermethod', 'priority')
        repo.check()
        repo.setupGrab()

class FastestMirror:

    def __init__(self, mirrorlist):
        global stop_after
        stop_after = stop_after == 0 and len(self.mirrorlist) - 1 or stop_after
        self.mirrorlist = mirrorlist
        self.results = {}
        self.count = 0

    def get_mirrorlist(self):
        self._poll_mirrors()
        mirrors = [(v, k) for k, v in self.results.items()]
        mirrors.sort()
        return [x[1] for x in mirrors]

    def _add_result(self, mirror, host, time):
        if verbose: print " * %s : %f" % (host, time)
        self.results[mirror] = time
        self.count += 1
        if stop_after and self.count >= stop_after:
            raise Exception

    def _poll_mirrors(self):
        for mirror in self.mirrorlist:
            AsyncMirrorConn(self, mirror)
        try:
            asyncore.loop(timeout=timeout, count=len(self.mirrorlist))
        except:
            pass

class AsyncMirrorConn(asyncore.dispatcher):

    def __init__(self, parent, mirror):
        asyncore.dispatcher.__init__(self)
        self.parent = parent
        self.mirror = mirror
        self.host = urlparse.urlparse(mirror)[1]
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.time_before = time.time()
        try:
            self.connect((self.host, 80))
        except:
            if verbose: print " * %s : dead" % self.host
            self.handle_close()

    def handle_connect(self):
        result = time.time() - self.time_before
        self.handle_close()
        self.parent._add_result(self.mirror, self.host, result)

    def handle_close(self):
        self.close()

    def handle_error(self):
        raise Exception

    def handle_read(self):
        pass

    def handle_write(self):
        pass

def main():
    global verbose
    verbose = True
    mirrorlist = []

    if len(sys.argv) == 1:
        print "Usage: %s <mirror1> [mirror2] ... [mirrorN]" % sys.argv[0]
        sys.exit(-1)
    del(sys.argv[0])

    for arg in sys.argv:
        mirrorlist.append(arg)

    print "Result: " + str(FastestMirror(mirrorlist).get_mirrorlist())

if __name__ == '__main__':
    main()

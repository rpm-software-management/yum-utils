#!/usr/bin/env python
# A plugin for the Yellowdog Updater Modified which sorts each repo's
# mirrorlist by connection speed prior to downloading packages.
#
# Configuration Options
# /etc/yum/pluginconf.d/fastestmirror.conf:
#   [main]
#   enabled=1
#   verbose=1
#   socket_timeout=3
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
import threading

from yum.plugins import TYPE_INTERFACE, TYPE_CORE

requires_api_version = '2.1'
plugin_type = (TYPE_INTERFACE, TYPE_CORE)

verbose = False
socket_timeout = 3

def init_hook(conduit):
    global verbose, socket_timeout
    verbose = conduit.confBool('main', 'verbose', default=False)
    socket_timeout = conduit.confInt('main', 'socket_timeout', default=3)

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
        self.mirrorlist = mirrorlist
        self.results = {}
        self.threads = []
        self.lock = threading.Lock()
        socket.setdefaulttimeout(socket_timeout)

    def get_mirrorlist(self):
        self._poll_mirrors()
        mirrors = [(v, k) for k, v in self.results.items()]
        mirrors.sort()
        return [x[1] for x in mirrors]

    def _poll_mirrors(self):
        for mirror in self.mirrorlist:
            pollThread = PollThread(self, mirror)
            pollThread.start()
            self.threads.append(pollThread)
        while len(self.threads) > 0:
            if self.threads[0].isAlive():
                self.threads[0].join()
            del(self.threads[0])

    def _add_result(self, mirror, host, time):
        self.lock.acquire()
        if verbose: print " * %s : %f secs" % (host, time)
        self.results[mirror] = time
        self.lock.release()

class PollThread(threading.Thread):

    def __init__(self, parent, mirror):
        threading.Thread.__init__(self)
        self.parent = parent
        self.mirror = mirror
        self.host = urlparse.urlparse(mirror)[1]

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            time_before = time.time()
            sock.connect((self.host, 80))
            result = time.time() - time_before
            sock.close()
            self.parent._add_result(self.mirror, self.host, result)
        except:
            if verbose:
                print " * %s : dead" % self.host

def main():
    global verbose
    verbose = True

    if len(sys.argv) == 1:
        print "Usage: %s <mirror1> [mirror2] ... [mirrorN]" % sys.argv[0]
        sys.exit(-1)

    del(sys.argv[0])
    mirrorlist = []

    for arg in sys.argv:
        mirrorlist.append(arg)

    print "Result: " + str(FastestMirror(mirrorlist).get_mirrorlist())

if __name__ == '__main__':
    main()

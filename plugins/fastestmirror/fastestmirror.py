#!/usr/bin/env python
#
# Version: 0.2.8
#
# A plugin for the Yellowdog Updater Modified which sorts each repo's
# mirrorlist by connection speed prior to download.
#
# To install this plugin, just drop it into /usr/lib/yum-plugins, and
# make sure you have 'plugins=1' in your /etc/yum.conf.  You also need to
# create the following configuration file, if not installed through an RPM:
#
#  /etc/yum/pluginconf.d/fastestmirror.conf:
#   [main]
#   enabled=1
#   verbose=1
#   socket_timeout=3
#   hostfilepath=/var/cache/yum/timedhosts
#   maxhostfileage=10
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
# (C) Copyright 2005 Luke Macken <lmacken@redhat.com>
#

import os
import sys
import time
import socket
import string
import urlparse
import datetime
import threading

from yum.plugins import TYPE_CORE

requires_api_version = '2.5'
plugin_type = (TYPE_CORE,)

verbose = False
socket_timeout = 3
timedhosts = {}
hostfilepath = ''
maxhostfileage = 10
loadcache = False

def init_hook(conduit):
    global verbose, socket_timeout, hostfilepath, maxhostfileage, loadcache
    verbose = conduit.confBool('main', 'verbose', default=False)
    socket_timeout = conduit.confInt('main', 'socket_timeout', default=3)
    hostfilepath = conduit.confString('main', 'hostfilepath',
            default='/var/cache/yum/timedhosts')
    maxhostfileage = conduit.confInt('main', 'maxhostfileage', default=10)
    if os.path.exists(hostfilepath) and get_hostfile_age() < maxhostfileage:
        loadcache = True

def clean_hook(conduit):
    if os.path.exists(hostfilepath):
        conduit.info(2, "Cleaning up list of fastest mirrors")
        os.unlink(hostfilepath)

def postreposetup_hook(conduit):
    global loadcache
    if loadcache:
        conduit.info(2, "Loading mirror speeds from cached hostfile")
        read_timedhosts()
    else:
        conduit.info(2, "Determining fastest mirrors")
    repomirrors = {}
    repos = conduit.getRepos()
    for repo in repos.listEnabled():
        if not repomirrors.has_key(str(repo)):
            repomirrors[str(repo)] = FastestMirror(repo.urls).get_mirrorlist()
        repo.urls = repomirrors[str(repo)]
        repo.failovermethod = 'priority'
        repo.check()
        repo.setupGrab()
    if not loadcache:
        write_timedhosts()

def read_timedhosts():
    global timedhosts
    try:
        hostfile = file(hostfilepath)
        for line in hostfile.readlines():
            host, time = line.split()
            timedhosts[host] = float(time)
        hostfile.close()
    except IOError:
        pass

def write_timedhosts():
    global timedhosts
    try:
        hostfile = file(hostfilepath, 'w')
        for host in timedhosts.keys():
            hostfile.write('%s %s\n' % (host, timedhosts[host]))
        hostfile.close()
    except IOError:
        pass

def get_hostfile_age():
    global hostfilepath
    timestamp = datetime.datetime.fromtimestamp(os.path.getmtime(hostfilepath))
    return (datetime.datetime.now() - timestamp).days

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
        global timedhosts
        self.lock.acquire()
        if verbose: print " * %s : %f secs" % (host, time)
        self.results[mirror] = time
        timedhosts[host] = time
        self.lock.release()

class PollThread(threading.Thread):

    def __init__(self, parent, mirror):
        threading.Thread.__init__(self)
        self.parent = parent
        self.mirror = mirror
        self.host = urlparse.urlparse(mirror)[1]
        uService = urlparse.urlparse(mirror)[0]
        if uService == "http":
            self.port = 80
        elif uService == "https":
            self.port = 443
        elif uService == "ftp":
            self.port = 21
        elif uService == "file":
            self.host = "127.0.0.1"
        else:
            self.port = -2

    def run(self):
        try:
            if timedhosts.has_key(self.host):
                result = timedhosts[self.host]
                if verbose:
                    print "%s already timed: %s" % (self.host, result)
            else:
                if self.host == "127.0.0.1" :
                    result = 0
                else:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    uPort = string.find(self.host,":")
                    if uPort > 0:
                        self.port = int(self.host[uPort+1:])
                        self.host = self.host[:uPort]
                    time_before = time.time()
                    sock.connect((self.host, self.port))
                    result = time.time() - time_before
                    sock.close()
            self.parent._add_result(self.mirror, self.host, result)
        except:
            if verbose:
                print " * %s : dead" % self.host
            self.parent._add_result(self.mirror, self.host, 99999999999)

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

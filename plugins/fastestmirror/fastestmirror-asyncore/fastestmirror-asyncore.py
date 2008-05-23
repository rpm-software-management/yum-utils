#!/usr/bin/env python
# This is a threadless prototype version of fastestmirror
#
# Version: 0.3.2
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
#   #exclude=.gov, facebook
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

"""
B{FastestMirror} is a Yum plugin which sorts each repository's mirrorlist
according to connection speed prior to download.
"""

import os
import sys
import time
import socket
import string
import urlparse
import datetime
import asyncore

from yum.plugins import TYPE_CORE

requires_api_version = '2.5'
plugin_type = (TYPE_CORE,)

verbose = False
socket_timeout = 1
timedhosts = {}
hostfilepath = ''
maxhostfileage = 10
loadcache = False
exclude = None

def init_hook(conduit):
    """
    This function initiliazes the variables required for running B{fastestmirror}
    module. The variables are initiliazed from the main section of the plugin file.

    There are no parameteres for this function. It uses global variables to
    communicate with other functions.

    This function refers:
        - L{get_hostfile_age}

    @param verbose : Verbosity of output.
    @type verbose : Boolean
    @param socket_timeout : The default timeout for a socket connection.
    @type socket_timeout : Integer
    @param hostfilepath : Absolute path to the plugin's cache file.
    @type hostfilepath : String
    @param maxhostfileage : Maximum age of the plugin's cache file.
    @type maxhostfileage : Integer
    @param loadcache : Fastest Mirrors to be loaded from plugin's cache or not.
    @type loadcache : Boolean

    """
    global verbose, socket_timeout, hostfilepath, maxhostfileage, loadcache
    global exclude
    verbose = conduit.confBool('main', 'verbose', default=False)
    socket_timeout = conduit.confInt('main', 'socket_timeout', default=3)
    hostfilepath = conduit.confString('main', 'hostfilepath',
            default='/var/cache/yum/timedhosts')
    maxhostfileage = conduit.confInt('main', 'maxhostfileage', default=10)
    exclude = conduit.confString('main', 'exclude', default=None)
    # If the file hostfilepath exists and is newer than the maxhostfileage,
    # then load the cache.
    if os.path.exists(hostfilepath) and get_hostfile_age() < maxhostfileage:
        loadcache = True

def clean_hook(conduit):
    """
    This function cleans the plugin cache file if exists. The function is called
    when C{yum [options] clean [plugins | all ]} is executed.
    """
    if os.path.exists(hostfilepath):
        conduit.info(2, "Cleaning up list of fastest mirrors")
        os.unlink(hostfilepath)

# Get the hostname from a url, stripping away any usernames/passwords
host = lambda mirror: mirror.split('/')[2].split('@')[-1]

def postreposetup_hook(conduit):
    """
    This function is called after Yum has initiliazed all the repository information.

    If cache file exists, this function will load the mirror speeds from the file,
    else it will determine the fastest mirrors afresh and write them back to the cache
    file.

    There are no parameteres for this function. It uses global variables to
    communicate with other functions.

    This function refers:
        - L{read_timedhosts()}
        - L{FastestMirror.get_mirrorlist()}
        - L{write_timedhosts()}

    @param loadcache : Fastest Mirrors to be loaded from plugin's cache file or not.
    @type loadcache : Boolean
    """
    global loadcache, exclude
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
        if exclude:
            for mirror in repomirrors[str(repo)]:
                if filter(lambda exp: exp in host(mirror),
                          exclude.replace(',', ' ').split()):
                    conduit.info(2, "Excluding mirror: %s" % host(mirror))
                    repomirrors[str(repo)].remove(mirror)
        repo.urls = repomirrors[str(repo)]
        if len(repo.urls):
            conduit.info(2, " * %s: %s" % (str(repo), host(repo.urls[0])))
        repo.failovermethod = 'priority'
        repo.check()
        repo.setupGrab()
    if not loadcache:
        write_timedhosts()

def read_timedhosts():
    """
    This function reads the time and hostname from the plugin's cache file and
    store them in C{timedhosts}.

    There are no parameteres for this function. It uses global variables to
    communicate with other functions.

    This function is referred by:
        - L{postreposetup_hook()}

    @param timedhosts : A list of time intervals to reach different hosts
    corresponding to the mirrors. The index of the list are hostnames.
    C{timedhosts[host] = time}.
    @type timedhosts : List
    """
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
    """
    This function writes the plugin's cache file with the entries in the
    C{timedhosts} list.

    There are no parameteres for this function. It uses global variables to
    communicate with other functions.

    This function is referred by:
        - L{postreposetup_hook()}

    @param timedhosts : A list of time intervals to reach different hosts
    corresponding to the mirrors. The index of the list are hostnames.
    C{timedhosts[host] = time}.
    @type timedhosts : List
    """
    global timedhosts
    try:
        hostfile = file(hostfilepath, 'w')
        for host in timedhosts.keys():
            hostfile.write('%s %s\n' % (host, timedhosts[host]))
        hostfile.close()
    except IOError:
        pass

def get_hostfile_age():
    """
    This function returns the current age of the plugin's cache file.

    There are no parameteres for this function. It uses global variables to
    communicate with other functions.

    This function is referred by:
        - L{init_hook()}

    @param hostfilepath : Absolute path to the plugin's cache file.
    @type hostfilepath : String
    @rtype: Integer
    @return: The age of the plugin's cache file.
    """
    global hostfilepath
    timestamp = datetime.datetime.fromtimestamp(os.path.getmtime(hostfilepath))
    return (datetime.datetime.now() - timestamp).days

class FastestMirror:
    """
    This is the helper class of B{fastestmirror} module. This class does
    all the processing of the response time calculation for all the mirrors
    of all the enabled Yum repositories.
    """

    def __init__(self, mirrorlist):
        """
        This is the initiliazer function of the B{L{FastestMirror}} class.

        @param mirrorlist : A list of mirrors for an enabled repository.
        @type mirrorlist : List
        """
        self.mirrorlist = mirrorlist
        self.results = {}
        socket.setdefaulttimeout(socket_timeout)

    def get_mirrorlist(self):
        """
        This function pings/polls all the mirrors in the list
        C{FastestMirror.mirrorlist} and returns the sorted list of mirrors
        according to the increasing response time of the mirrors.

        This function refers:
            - L{FastestMirror._poll_mirrors()}

        This function is referred by:
            - L{postreposetup_hook()}
            - L{main()}

        @rtype: List
        @return: The list of mirrors sorted according to the increasing
        response time.
        """
        self._poll_mirrors()
        mirrors = [(v, k) for k, v in self.results.items()]
        mirrors.sort()
        return [x[1] for x in mirrors]

    def _poll_mirrors(self):
        """
        This function uses L{PollThread} class to ping/poll individual mirror
        in parallel.

        This function refers:
            - L{PollThread.run()}

        This function is referred by:
            - L{FastestMirror.get_mirrorlist()}
        """
        for mirror in self.mirrorlist:
            AsyncMirrorConn(self, mirror)
        count = len(self.mirrorlist)
        if count > 10: count = 10
        asyncore.loop(timeout=socket_timeout, count=count)


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
            self.close()

    def handle_connect(self):
        result = time.time() - self.time_before
        self.handle_close()
        self._add_result(self.mirror, self.host, result)

    def handle_close(self):
        self.close()

    def handle_read(self):
        pass

    def handle_write(self):
        pass


    def _add_result(self, mirror, host, time):
        """
        This function is called by L{PollThread.run()} to add details of a
        mirror in C{FastestMirror.results} dictionary.

        This function is referred by:
            - L{PollThread.run()}

        @param mirror : The mirror that was polled for response time.
        @type mirror : String
        @param host : The hostname of the mirror.
        @type host : String
        @param time : The response time of the mirror.
        @type time : Integer
        @param timedhosts : A list of time intervals to reach different hosts
        corresponding to the mirrors. The index of the list are hostnames.
        @type timedhosts : List
        """
        global timedhosts
        if verbose: print " * %s : %f secs" % (host, time)
        self.parent.results[mirror] = time
        timedhosts[host] = time


def main():
    """
    This is the main function for B{fastestmirror} module.

    This function explains the usage of B{fastestmirror} module. Also parses
    the command line arguments.

    This function refers:
        - L{FastestMirror.get_mirrorlist()}
    """
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

#!/usr/bin/python
#
# Version: 0.3.3
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
#   hostfilepath=timedhosts
#   maxhostfileage=10
#   maxthreads=15
#   #exclude=.gov, facebook
#   #include_only=.nl,.de,.uk,.ie
#   #prefer=your.favourite.mirror
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
import threading
import re

from yum.plugins import TYPE_CORE

requires_api_version = '2.5'
plugin_type = (TYPE_CORE,)

verbose = False
always_print_best_host = True
socket_timeout = 3
timedhosts = {}
hostfilepath = ''
maxhostfileage = 10
loadcache = False
maxthreads = 15
exclude = None
include_only = None
prefer = None
downgrade_ftp = True
done_sock_timeout = False
done_repos = set()

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
    global maxthreads, exclude, include_only, prefer, downgrade_ftp, always_print_best_host
    if hasattr(conduit, 'registerPackageName'):
        conduit.registerPackageName("yum-plugin-fastestmirror")
    verbose = conduit.confBool('main', 'verbose', default=False)
    always_print_best_host = conduit.confBool('main', 'always_print_best_host',
                                              default=True)
    socket_timeout = conduit.confInt('main', 'socket_timeout', default=3)
    hostfilepath = conduit.confString('main', 'hostfilepath',
            default='timedhosts')
    maxhostfileage = conduit.confInt('main', 'maxhostfileage', default=10)
    maxthreads = conduit.confInt('main', 'maxthreads', default=10)
    exclude = conduit.confString('main', 'exclude', default=None)
    include_only = conduit.confString('main', 'include_only', default=None)
    prefer = conduit.confString('main', 'prefer', default='no.prefer.mirror')
    downgrade_ftp = conduit.confBool('main', 'downgrade_ftp', default=True)

def clean_hook(conduit):
    """
    This function cleans the plugin cache file if exists. The function is called
    when C{yum [options] clean [plugins | all ]} is executed.
    """
    global hostfilepath
    if hostfilepath and hostfilepath[0] != '/':
        hostfilepath = conduit._base.conf.cachedir + '/' + hostfilepath
    if os.path.exists(hostfilepath):
        conduit.info(2, "Cleaning up list of fastest mirrors")
        try:
            os.unlink(hostfilepath)
        except Exception, e:
            conduit.info(2, "Cleanup failed: %s" % e)

# Get the hostname from a url, stripping away any usernames/passwords
host = lambda mirror: mirror.split('/')[2].split('@')[-1]

def _can_write_results(fname):
    if not os.path.exists(fname):
        try:
            hostfile = file(hostfilepath, 'w')
            return True
        except:
            return False

    return os.access(fname, os.W_OK)

def _len_non_ftp(urls):
    ''' Count the number of urls, which aren't ftp. '''
    num = 0
    for url in urls:
        if url.startswith("ftp:"):
            continue
        num += 1
    return num

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
    global loadcache, exclude, include_only, prefer, hostfilepath

    if hostfilepath and hostfilepath[0] != '/':
        hostfilepath = conduit._base.conf.cachedir + '/' + hostfilepath
    # If the file hostfilepath exists and is newer than the maxhostfileage,
    # then load the cache.
    if os.path.exists(hostfilepath) and get_hostfile_age() < maxhostfileage:
        loadcache = True

    opts, commands = conduit.getCmdLine()
    if conduit._base.conf.cache or not _can_write_results(hostfilepath):
        return

    if done_repos:
        conduit.info(2, "Checking for new repos for mirrors")
    elif loadcache:
        conduit.info(2, "Loading mirror speeds from cached hostfile")
        read_timedhosts()
    else:
        conduit.info(2, "Determining fastest mirrors")
    repomirrors = {}
    repos = conduit.getRepos()

    #  First do all of the URLs as one big list, this way we get as much
    # parallelism as possible (if we need to do the network tests).
    all_urls = []
    for repo in repos.listEnabled():
        if repo.id in done_repos:
            continue
        if downgrade_ftp and _len_non_ftp(repo.urls) == 1:
            continue
        if len(repo.urls) == 1:
            continue
        all_urls.extend(repo.urls)
    all_urls = FastestMirror(all_urls).get_mirrorlist()

    #  This should now just be looking up the cached times.
    for repo in repos.listEnabled():
        if repo.id in done_repos:
            continue
        if downgrade_ftp and _len_non_ftp(repo.urls) == 1:
            repo.urls = sorted(repo.urls, reverse=True) # ftp comes before http
            continue
        if len(repo.urls) == 1:
            continue
        if str(repo) not in repomirrors:
            repomirrors[str(repo)] = FastestMirror(repo.urls).get_mirrorlist()
        if include_only:
            def includeCheck(mirror):
                if filter(lambda exp: re.search(exp, host(mirror)),
                          include_only.replace(',', ' ').split()):
                    conduit.info(2, "Including mirror: %s" % host(mirror))
                    return True
                return False
            repomirrors[str(repo)] = filter(includeCheck,repomirrors[str(repo)])
        else:
            if exclude:
                def excludeCheck(mirror):
                    if filter(lambda exp: re.search(exp, host(mirror)),
                              exclude.replace(',', ' ').split()):
                        conduit.info(2, "Excluding mirror: %s" % host(mirror))
                        return False
                    return True
                repomirrors[str(repo)] = filter(excludeCheck,repomirrors[str(repo)])
        repo.urls = repomirrors[str(repo)]
        if len(repo.urls):
            lvl = 3
            if always_print_best_host:
                lvl = 2
            conduit.info(lvl, " * %s: %s" % (str(repo), host(repo.urls[0])))
        repo.failovermethod = 'priority'
        repo.check()
        repo.setupGrab()
        done_repos.add(repo.id)
    if done_sock_timeout:
        socket.setdefaulttimeout(None)

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
        for host in timedhosts:
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
        self.threads = []

    # If we don't spawn any threads, we don't need locking...
    def _init_lock(self):
        if not hasattr(self, '_results_lock'):
            self._results_lock = threading.Lock()
            global done_sock_timeout
            done_sock_timeout = True
            socket.setdefaulttimeout(socket_timeout)

    def _acquire_lock(self):
        if hasattr(self, '_results_lock'):
            self._results_lock.acquire()
    def _release_lock(self):
        if hasattr(self, '_results_lock'):
            self._results_lock.release()

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
        if not downgrade_ftp:
            mirrors = [(v, k) for k, v in self.results.items()]
        else:
            # False comes before True
            mirrors = [(k.startswith("ftp"), v, k) for k, v in
                       self.results.items()]
        mirrors.sort()
        return [x[-1] for x in mirrors]

    def _poll_mirrors(self):
        """
        This function uses L{PollThread} class to ping/poll individual mirror
        in parallel.

        This function refers:
            - L{PollThread.run()}

        This function is referred by:
            - L{FastestMirror.get_mirrorlist()}
        """
        global maxthreads
        for mirror in self.mirrorlist:
            if len(self.threads) > maxthreads:
                if self.threads[0].isAlive():
                    self.threads[0].join()
                del self.threads[0]

            if mirror.startswith("file:"):
                mhost = "127.0.0.1"
            else:
                mhost = host(mirror)

            if mhost in timedhosts:
                result = timedhosts[mhost]
                if verbose:
                    print "%s already timed: %s" % (mhost, result)
                self._add_result(mirror, mhost, result)
            elif mhost in ("127.0.0.1", "::1", "localhost", prefer):
                self._add_result(mirror, mhost, 0)
            else:
                # No cached info. so spawn a thread and find the info. out
                self._init_lock()
                pollThread = PollThread(self, mirror)
                pollThread.start()
                self.threads.append(pollThread)
        while len(self.threads) > 0:
            if self.threads[0].isAlive():
                self.threads[0].join()
            del self.threads[0]

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
        self._acquire_lock()
        if verbose: print " * %s : %f secs" % (host, time)
        self.results[mirror] = time
        timedhosts[host] = time
        self._release_lock()

class PollThread(threading.Thread):
    """
    B{PollThread} class implements C{threading.Thread} class. This class
    provides the functionalities to ping/poll the mirrors in parallel.
    """

    def __init__(self, parent, mirror):
        """
        It is initiliazer function for B{L{PollThread}} class. This function
        initiliazes the service ports for different webservices.

        @param parent : The parent class.
        @type parent : Class
        @param mirror : The mirror of a repository.
        @type mirror : String
        """
        threading.Thread.__init__(self)
        self.parent = parent
        self.mirror = mirror
        self.host = host(mirror)
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
        """
        The C{threading.Thread.run()} function is being overridden here.
        This function pings/polls a mirror and add the details of that
        mirror to the C{FastestMirror.results} dictionary.

        The response time of any mirror is '99999999999' if any exception
        occurs during polling.

        This function refers:
            - L{FastestMirror._add_result()}

        This function is referred by:
            - L{FastestMirror._poll_mirrors()}
        """
        try:
            if self.host in timedhosts:
                result = timedhosts[self.host]
                if verbose:
                    print "%s already timed: %s" % (self.host, result)
            else:
                if self.host in ("127.0.0.1", "::1", "localhost", prefer):
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

    mirrorlist = sys.argv[1:]
    print "Result: " + str(FastestMirror(mirrorlist).get_mirrorlist())

if __name__ == '__main__':
    main()

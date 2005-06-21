#!/usr/bin/python -t

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
# seth vidal 2005 (c) etc etc


#Read in the metadata of a series of repositories and check all the
#   dependencies in all packages for resolution. Print out the list of
#   packages with unresolved dependencies


import yum
import yum.Errors
import sys
import os
from stat import *
import pwd
import glob

from optparse import OptionParser
import tempfile
import rpmUtils.arch
from yum.constants import *


def getCacheDir():
    """return a path to a valid and safe cachedir - only used when not running
       as root or when --tempcache is set"""
    
    tmpdir='/var/tmp'
    uid = os.geteuid()
    try:
        usertup = pwd.getpwuid(uid)
        username = usertup[0]
    except KeyError:
        return None # if it returns None then, well, it's bollocksed

    # check for /var/tmp/yum-username-* - 
    prefix = 'yum-%s-' % username    
    dirpath = '%s/%s*' % (tmpdir, prefix)
    cachedirs = glob.glob(dirpath)
    
    for thisdir in cachedirs:
        stats = os.stat(thisdir)        
        if S_ISDIR(stats[0]) and S_IMODE(stats[0]) == 448 and stats[4] == uid:
            print thisdir
            return thisdir

    # make the dir (tempfile.mkdtemp())
    cachedir = tempfile.mkdtemp(prefix=prefix, dir=tmpdir)
    return cachedir
    
def evrTupletoVer(tuple):
    """convert and evr tuple to a version string, return None if nothing
       to convert"""
    
    e, v,r = tuple
    if v is None:
        return None
    
    val = ''
    if e is not None:
        val = '%s:%s' % (e, v)
    
    if r is not None:
        val = '%s-%s' % (val, r)
    
    return val
    
def parseArgs():
    usage = "usage: %s [-c <config file>] [-a <arch>] [-r <repoid>] [-r <repoid2>]" % sys.argv[0]
    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--config", default='/etc/yum.conf',
        help='config file to use (defaults to /etc/yum.conf)')
    parser.add_option("-a", "--arch", default=None,
        help='check as if running the specified arch (default: current arch)')
    parser.add_option("-r", "--repoid", default=[], action='append',
        help="specify repo ids to query, can be specified multiple times (default is all enabled)")
    parser.add_option("-t", "--tempcache", default=False, action="store_true", 
        help="Use a temp dir for storing/accessing yum-cache")
    parser.add_option("-q", "--quiet", default=0, action="store_true", 
                      help="quiet (no output to stderr)")
        
    (opts, args) = parser.parse_args()
    return (opts, args)

class YumQuiet(yum.YumBase):
    def __init__(self):
        yum.YumBase.__init__(self)
    
    def log(self, value, msg):
        pass

def main():
    (opts, cruft) = parseArgs()
    my = YumQuiet()
    my.doConfigSetup(fn = opts.config)
    if hasattr(my.repos, 'sqlite'):
        my.repos.sqlite = False
        my.repos._selectSackType()

    if opts.repoid:
        for repo in my.repos.repos.values():
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                repo.enable()

    if os.geteuid() != 0 or opts.tempcache:
        cachedir = getCacheDir()
        if cachedir is None:
            print "Error: Could not make cachedir, exiting"
            sys.exit(50)
            
        my.repos.setCacheDir(cachedir)
        
    my.doRepoSetup()
    if not opts.quiet:
        print 'Reading in repository metadata - please wait....'
    my.doSackSetup(rpmUtils.arch.getArchList(opts.arch))
    for repo in my.repos.listEnabled():
            
        try:
            my.repos.populateSack(which=[repo.id], with='filelists')
        except yum.Errors.RepoError, e:
            print 'Filelists not available for repo: %s' % repo
            print 'Some dependencies may not be complete for this repository'
            print 'Run as root to get all dependencies'

    unresolved = {}
    # Cache resolved dependencies for speed
    resolved = {}
    
    if not opts.quiet:
        print 'Checking Dependencies'
        
    for pkg in my.pkgSack:
        for (req, flags, (reqe, reqv, reqr)) in pkg.returnPrco('requires'):
            if req.startswith('rpmlib'): continue # ignore rpmlib deps
            
            ver = evrTupletoVer((reqe, reqv, reqr))
            if resolved.has_key((req,flags,ver)):
                continue
            try:
                resolve_sack = my.whatProvides(req, flags, ver)
            except yum.Errors.RepoError, e:
                pass
            
            if len(resolve_sack) < 1:
                if not unresolved.has_key(pkg):
                    unresolved[pkg] = []
                unresolved[pkg].append((req, flags, ver))
            else:
                resolved[(req,flags,ver)] = 1
    

    num = len(my.pkgSack)
    repos = my.repos.listEnabled()

    if not opts.quiet:
        print 'Repos looked at: %s' % len(repos)
        for repo in repos:
            print '   %s' % repo
        print 'Num Packages in Repos: %s' % num
    
    
    pkgs = unresolved.keys()
    pkgs.sort()
    for pkg in pkgs:
        print 'package: %s from %s\n  unresolved deps: ' % (pkg, pkg.repoid)
        for (n, f, v) in unresolved[pkg]:
            req = '%s' % n
            if f: 
                flag = LETTERFLAGS[f]
                req = '%s %s'% (req, flag)
            if v:
                req = '%s %s' % (req, v)
            
            print '     %s' % req
    
if __name__ == "__main__":
    main()


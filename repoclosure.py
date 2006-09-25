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

import sys
import os

import logging
import yum
import yum.Errors
from yum.misc import getCacheDir
from optparse import OptionParser
import rpmUtils.arch
from yum.constants import *
from yum.packageSack import ListPackageSack

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
    parser.add_option("-n", "--newest", default=0, action="store_true",
                      help="check only the newest packages in the repos")
    (opts, args) = parser.parse_args()
    return (opts, args)

class RepoClosure(yum.YumBase):
    def __init__(self, arch = None, config = "/etc/yum.conf"):
        yum.YumBase.__init__(self)
        self.logger = logging.getLogger("yum.verbose.repoclosure")
        self.arch = arch
        self.doConfigSetup(fn = config,init_plugins=False)
        if hasattr(self.repos, 'sqlite'):
            self.repos.sqlite = False
            self.repos._selectSackType()
    
    def evrTupletoVer(self,tuple):
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
    
    def readMetadata(self):
        self.doRepoSetup()
        self.doSackSetup(rpmUtils.arch.getArchList(self.arch))
        for repo in self.repos.listEnabled():
            self.repos.populateSack(which=[repo.id], with='filelists')

    def getBrokenDeps(self, newest=False):
        unresolved = {}
        resolved = {}
        if newest:
            pkgs = self.pkgSack.returnNewestByNameArch()
        else:
            pkgs = self.pkgSack

        mypkgSack = ListPackageSack(pkgs)
        pkgtuplist = mypkgSack.simplePkgList()
        
        for pkg in pkgs:
            for (req, flags, (reqe, reqv, reqr)) in pkg.returnPrco('requires'):
                if req.startswith('rpmlib'): continue # ignore rpmlib deps
            
                ver = self.evrTupletoVer((reqe, reqv, reqr))
                if resolved.has_key((req,flags,ver)):
                    continue
                try:
                    resolve_sack = self.whatProvides(req, flags, ver)
                except yum.Errors.RepoError, e:
                    pass
            
                if len(resolve_sack) < 1:
                    if not unresolved.has_key(pkg):
                        unresolved[pkg] = []
                    unresolved[pkg].append((req, flags, ver))
                    continue
                    
                if newest:
                    resolved_by_newest = False
                    for po in resolve_sack:# look through and make sure all our answers are newest-only
                        if po.pkgtup in pkgtuplist:
                            resolved_by_newest = True
                            break

                    if resolved_by_newest:                    
                        resolved[(req,flags,ver)] = 1
                    else:
                        if not unresolved.has_key(pkg):
                            unresolved[pkg] = []
                        unresolved[pkg].append((req, flags, ver))                        
                        
        return unresolved
    

def main():
    (opts, cruft) = parseArgs()
    my = RepoClosure(arch = opts.arch, config = opts.config)
    
    if opts.repoid:
        for repo in my.repos.repos.values():
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                repo.enable()

    if os.geteuid() != 0 or opts.tempcache:
        cachedir = getCacheDir()
        if cachedir is None:
            my.logger.error("Error: Could not make cachedir, exiting")
            sys.exit(50)
            
        my.repos.setCacheDir(cachedir)

    if not opts.quiet:
        my.logger.info('Reading in repository metadata - please wait....')

    try:
        my.readMetadata()
    except yum.Errors.RepoError, e:
        my.logger.info('Filelists not available for repo: %s' % repo)
        my.logger.info('Some dependencies may not be complete for this repository')
        my.logger.info('Run as root to get all dependencies or use -t to enable a user temp cache')

    if not opts.quiet:
        my.logger.info('Checking Dependencies')

    baddeps = my.getBrokenDeps(opts.newest)
    if opts.newest:
        num = len(my.pkgSack.returnNewestByNameArch())
    else:
        num = len(my.pkgSack)
        
    repos = my.repos.listEnabled()

    if not opts.quiet:
        my.logger.info('Repos looked at: %s' % len(repos))
        for repo in repos:
            my.logger.info('   %s' % repo)
        my.logger.info('Num Packages in Repos: %s' % num)
    
    pkgs = baddeps.keys()
    pkgs.sort()
    for pkg in pkgs:
        my.logger.info('package: %s from %s\n  unresolved deps: ' % (pkg, pkg.repoid))
        for (n, f, v) in baddeps[pkg]:
            req = '%s' % n
            if f: 
                flag = LETTERFLAGS[f]
                req = '%s %s'% (req, flag)
            if v:
                req = '%s %s' % (req, v)
            
            my.logger.info('     %s' % req)

if __name__ == "__main__":
    main()
        

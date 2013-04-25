#!/usr/bin/python -t

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
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
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
import rpmUtils.updates
from yum.constants import *
from yum.packageSack import ListPackageSack

def parseArgs():
    usage = """
    Read in the metadata of a series of repositories and check all the   
    dependencies in all packages for resolution. Print out the list of
    packages with unresolved dependencies
    
    %s [-c <config file>] [-a <arch>] [-l <lookaside>] [-r <repoid>] [-r <repoid2>]
    """ % sys.argv[0]
    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--config", default='/etc/yum.conf',
        help='config file to use (defaults to /etc/yum.conf)')
    parser.add_option("-a", "--arch", default=[], action='append',
        help='check packages of the given archs, can be specified multiple ' +
             'times (default: current arch)')
    parser.add_option("--basearch", default=None, 
                      help="set the basearch for yum to run as")
    parser.add_option("-b", "--builddeps", default=False, action="store_true",
        help='check build dependencies only (needs source repos enabled)')
    parser.add_option("-l", "--lookaside", default=[], action='append',
        help="specify a lookaside repo id to query, can be specified multiple times")
    parser.add_option("-r", "--repoid", default=[], action='append',
        help="specify repo ids to query, can be specified multiple times (default is all enabled)")
    parser.add_option("-t", "--tempcache", default=False, action="store_true", 
        help="Use a temp dir for storing/accessing yum-cache")
    parser.add_option("-q", "--quiet", default=0, action="store_true", 
                      help="quiet (no output to stderr)")
    parser.add_option("-n", "--newest", default=0, action="store_true",
                      help="check only the newest packages in the repos")
    parser.add_option("--repofrompath", action="append",
                      help="specify repoid & paths of additional repositories - unique repoid and path required, can be specified multiple times. Example. --repofrompath=myrepo,/path/to/repo")
    parser.add_option("-p", "--pkg", action="append",
                      help="check closure for this package only")
    parser.add_option("-g", "--group", action="append",
                      help="check closure for packages in this group only")
    (opts, args) = parser.parse_args()
    return (opts, args)

#  Note that this is a "real" API, used by spam-o-matic etc.
# so we have to do at least some API guarantee stuff.
class RepoClosure(yum.YumBase):
    def __init__(self, arch=[], config="/etc/yum.conf", builddeps=False, pkgonly=None,
                 basearch=None, grouponly=None):
        yum.YumBase.__init__(self)
        if basearch:
            self.preconf.arch = basearch
        self.logger = logging.getLogger("yum.verbose.repoclosure")
        self.lookaside = []
        self.builddeps = builddeps
        self.pkgonly = pkgonly
        self.grouponly = grouponly
        self.doConfigSetup(fn = config,init_plugins=False)
        self._rc_arches = arch

        if hasattr(self.repos, 'sqlite'):
            self.repos.sqlite = False
            self.repos._selectSackType()
    
    def evrTupletoVer(self,tup):
        """convert an evr tuple to a version string, return None if nothing
        to convert"""
    
        e, v, r = tup

        if v is None:
            return None
    
        val = v
        if e is not None:
            val = '%s:%s' % (e, v)
    
        if r is not None:
            val = '%s-%s' % (val, r)
    
        return val
    
    def readMetadata(self):
        self.doRepoSetup()
        archs = []
        if not self._rc_arches:
            archs.extend(self.arch.archlist)
        else:
            for arch in self._rc_arches:
                archs.extend(self.arch.get_arch_list(arch))

        if self.builddeps and 'src' not in archs:
            archs.append('src')
        self.doSackSetup(archs)
        for repo in self.repos.listEnabled():
            self.repos.populateSack(which=[repo.id], mdtype='filelists')

    def getBrokenDeps(self, newest=False):
        unresolved = {}
        resolved = {}
        pkgs = self.pkgSack
        if newest:
            pkgs = self.pkgSack.returnNewestByNameArch()
            mypkgSack = ListPackageSack(pkgs)
            pkgtuplist = mypkgSack.simplePkgList()
            
            # toss out any of the obsoleted pkgs so we can't depsolve with them
            self.up = rpmUtils.updates.Updates([], pkgtuplist)
            self.up.rawobsoletes = mypkgSack.returnObsoletes()
            for pkg in pkgs:
                fo = self.up.checkForObsolete([pkg.pkgtup])
                if fo:
                    # useful debug to make sure the obsoletes is sane
                    #print "ignoring obsolete pkg %s" % pkg
                    #for i in fo[pkg.pkgtup]:
                    #    print i
                    self.pkgSack.delPackage(pkg)

            # we've deleted items so remake the pkgs
            pkgs = self.pkgSack.returnNewestByNameArch()
            pkgtuplist = mypkgSack.simplePkgList()
        
        if self.builddeps:
            pkgs = filter(lambda x: x.arch == 'src', pkgs)

        pkglist = self.pkgonly
        if self.grouponly:
            if not pkglist:
                pkglist = []
            for group in self.grouponly:
                groupobj = self.comps.return_group(group)
                if not groupobj:
                    continue
                pkglist.extend(groupobj.packages)

        if pkglist:
            pkgs = filter(lambda x: x.name in pkglist, pkgs)

        for pkg in pkgs:
            if pkg.repoid in self.lookaside:
                # don't attempt to resolve dependency issues for
                # packages from lookaside repositories
                continue
            for (req, flags, (reqe, reqv, reqr)) in pkg.returnPrco('requires'):
                if req.startswith('rpmlib'): continue # ignore rpmlib deps
            
                ver = self.evrTupletoVer((reqe, reqv, reqr))
                if (req,flags,ver) in resolved:
                    continue
                
                resolve_sack = [] # make it empty
                try:
                    resolve_sack = self.whatProvides(req, flags, ver)
                except yum.Errors.RepoError, e:
                    pass
            
                if len(resolve_sack) < 1:
                    if pkg not in unresolved:
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
                        if pkg not in unresolved:
                            unresolved[pkg] = []
                        unresolved[pkg].append((req, flags, ver))
                        
        return unresolved
    

def main():
    (opts, cruft) = parseArgs()
    my = RepoClosure(arch=opts.arch, 
                     config=opts.config, 
                     builddeps=opts.builddeps,
                     pkgonly=opts.pkg,
                     grouponly=opts.group,
                     basearch=opts.basearch)

    if opts.repofrompath:
        # setup the fake repos
        for repo in opts.repofrompath:
            repoid,repopath = tuple(repo.split(','))
            if repopath.startswith('http') or repopath.startswith('ftp') or repopath.startswith('file:'):
                baseurl = repopath
            else:
                repopath = os.path.abspath(repopath)                
                baseurl = 'file://' + repopath
                
            newrepo = yum.yumRepo.YumRepository(repoid)
            newrepo.name = repopath
            newrepo.baseurl = baseurl
            newrepo.basecachedir = my.conf.cachedir
            newrepo.metadata_expire = 0
            newrepo.timestamp_check = False
            my.repos.add(newrepo)
            my.repos.enableRepo(newrepo.id)
            my.logger.info( "Added %s repo from %s" % (repoid,repopath))
    
    if opts.repoid:
        for repo in my.repos.repos.values():
            if ((repo.id not in opts.repoid) and
                (repo.id not in opts.lookaside)):
                repo.disable()
            else:
                repo.enable()

    if opts.lookaside:
        my.lookaside = opts.lookaside

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
        my.logger.info(e)
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
    
    def sortbyname(a,b):
        return cmp(a.__str__(),b.__str__())
    
    pkgs.sort(sortbyname)
    
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
    if baddeps:
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except (yum.Errors.YumBaseError, ValueError), e:
        print >> sys.stderr, str(e)
        sys.exit(2)

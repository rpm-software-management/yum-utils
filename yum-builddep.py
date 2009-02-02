#!/usr/bin/python -tt

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

import sys
sys.path.insert(0,'/usr/share/yum-cli')

import yum
from yum.misc import setup_locale
import yum.Errors
from utils import YumUtilBase

import logging
import rpmUtils


class YumBuildDep(YumUtilBase):
    NAME = 'yum-builddep'
    VERSION = '1.0'
    USAGE = '"usage: yum-builddep [options] package1 [package2] [package..]'
    
    def __init__(self):
        YumUtilBase.__init__(self,
                             YumBuildDep.NAME,
                             YumBuildDep.VERSION,
                             YumBuildDep.USAGE)
        self.logger = logging.getLogger("yum.verbose.cli.yumbuildep")                             
        # Add util commandline options to the yum-cli ones
        self.optparser = self.getOptionParser() 
        self.main()

    def main(self):
        # Parse the commandline option and setup the basics.
        try:
            opts = self.doUtilConfigSetup()
        except yum.Errors.RepoError, e:
            self.logger.error("Cannot handle specific enablerepo/disablerepo options.")
            sys.exit(50)

        # Check if there is anything to do.
        if len(self.cmds) < 1: 
            self.optparser.print_help()
            sys.exit(0)

        if self.conf.uid != 0:
            self.logger.error("Error: You must be root to install packages")
            sys.exit(1)

        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup()
        # Do the real action
        # solve for each srpm and put the pkgs into a ts
        try:
            self.get_build_deps()
        except yum.Errors.MiscError, e:
            msg = "There was a problem getting the build deps, exiting:\n   %s" % e
            self.logger.error(msg)
            sys.exit(1)

        self.buildTransaction()
        if len(self.tsInfo) < 1:
            print 'No uninstalled build requires'
            sys.exit()
            
        self.doTransaction()
        
    def setupSourceRepos(self):
        # enable the -source repos for enabled primary repos
        archlist = rpmUtils.arch.getArchList() + ['src']    
        for repo in self.repos.listEnabled():
            if not repo.id.endswith('-source'):
                srcrepo = '%s-source' % repo.id
            else:
                repo.close()
                self.repos.disableRepo(repo.id)
                srcrepo = repo.id
            
            for r in self.repos.findRepos(srcrepo):
                if r in self.repos.listEnabled():
                    continue
                self.logger.info('Enabling %s repository' % r.id)
                r.enable()
                # Setup the repo, without a cache
                r.setup(0)
                # Setup pkgSack with 'src' in the archlist
                try:
                    self._getSacks(archlist=archlist,thisrepo=r.id)
                except yum.Errors.RepoError, e:
                    print "Could not setup repo %s: %s" % (r.id, e)
                    sys.exit(1)

    # go through each of the pkgs, figure out what they are/where they are 
    # if they are not a local package then run
        # Setup source repos
        #self.setupSourceRepos()
    # get all of their deps
    # throw them into a ts
    # run the ts
    
    def get_build_deps(self):
        srcnames = []
        srpms = []
        for arg in self.cmds:
            if arg.endswith('.src.rpm'):
                try:
                    srpms.append(yum.packages.YumLocalPackage(self.ts, arg))
                except yum.Errors.MiscError, e:
                    self.logger.error("Error: Could not open %s" % arg)
                    raise
            elif arg.endswith('.src'):
                srcnames.append(arg)
            else:
                srcnames.append('%s.src' % arg)

        if srcnames:
            self.setupSourceRepos()
            exact, match, unmatch = yum.packages.parsePackages(self.pkgSack.returnPackages(), srcnames, casematch=1)
            srpms += exact + match
            
            if len(unmatch):
                exact, match, unmatch = yum.packages.parsePackages(self.rpmdb.returnPackages(), unmatch, casematch=1)
                if len(unmatch):
                    self.logger.error("No such package(s): %s" %
                                      ", ".join(unmatch))
                    sys.exit(1)

        for srpm in srpms:
            for dep in srpm.requiresList():
                if dep.startswith("rpmlib("): 
                    continue
                try:
                    pkg = self.returnPackageByDep(dep)
                    print pkg
                    if not self.rpmdb.installed(name=pkg.name):
                        self.tsInfo.addInstall(pkg)
                    
                except yum.Errors.YumBaseError, e:
                    self.logger.error("Error: %s" % e)
                    sys.exit(1)
    
    
if __name__ == '__main__':
    setup_locale()
    util = YumBuildDep()
        
       

#!/usr/bin/python -tt

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

import sys
sys.path.insert(0,'/usr/share/yum-cli')

import yum
from yum.misc import setup_locale
from yum.i18n import exception2msg
import yum.Errors
from utils import YumUtilBase

import logging
import rpmUtils
import rpm

rhn_source_repos = False

# Copied from yumdownloader (need a yum-utils python module ;)
# This is to fix Bug 469
# To convert from a pkg to a source pkg, we have a problem in that all we have
# is "sourcerpm", which can be a different nevra ... but just to make it fun
# the epoch isn't in the name. So we use rpmUtils.miscutils.splitFilename
# and ignore the arch/epoch ... and hope we get the right thing.
# Eg. run:
# for pkg in yb.pkgSack.returnPackages():
#     if pkg.version not in pkg.sourcerpm:
#         print pkg, pkg.sourcerpm
def _best_convert_pkg2srcpkgs(self, opts, pkg):
    if pkg.arch == 'src':
        return [pkg]

    (n,v,r,e,a) = rpmUtils.miscutils.splitFilename(pkg.sourcerpm)
    src = self.pkgSack.searchNevra(name=n, ver=v, rel=r, arch='src')
    if src == []:
        self.logger.error('No source RPM found for %s' % str(pkg))

    return src


class YumBuildDep(YumUtilBase):
    NAME = 'yum-builddep'
    VERSION = '1.0'
    USAGE = 'yum-builddep [options] package1 [package2] [package..]'
    
    def __init__(self):
        YumUtilBase.__init__(self,
                             YumBuildDep.NAME,
                             YumBuildDep.VERSION,
                             YumBuildDep.USAGE)
        self.logger = logging.getLogger("yum.verbose.cli.yumbuildep")                             
        # Add util commandline options to the yum-cli ones
        self.optparser = self.getOptionParser() 
        if hasattr(rpm, 'reloadConfig'):
            self.optparser.add_option("--target",
                              help="set target architecture for spec parsing")
        self.main()

    def main(self):
        # Parse the commandline option and setup the basics.
        try:
            opts = self.doUtilConfigSetup()
        except yum.Errors.RepoError, e:
            self.logger.error("Cannot handle specific enablerepo/disablerepo options.")
            sys.exit(50)

        # turn of our local gpg checking for opening the srpm if it is turned
        # off for repos :)
        if (opts.nogpgcheck or
            not self.conf.localpkg_gpgcheck or not self.conf.gpgcheck):
            self.ts.pushVSFlags((rpm._RPMVSF_NOSIGNATURES|rpm._RPMVSF_NODIGESTS))

        # Check if there is anything to do.
        if len(self.cmds) < 1: 
            print self.optparser.format_help()
            sys.exit(0)

        if self.conf.uid != 0:
            self.logger.error("Error: You must be root to install packages")
            sys.exit(1)

        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup()
        # Do the real action
        # solve for each srpm and put the pkgs into a ts
        try:
            self.get_build_deps(opts)
        except yum.Errors.MiscError, e:
            msg = "There was a problem getting the build deps, exiting:\n   %s" % e
            self.logger.error(msg)
            sys.exit(1)

        if hasattr(self, 'doUtilBuildTransaction'):
            errc = self.doUtilBuildTransaction()
            if errc:
                sys.exit(errc)
        else:
            try:
                self.buildTransaction()
            except yum.Errors.YumBaseError, e:
                self.logger.critical("Error building transaction: %s" % e)
                sys.exit(1)

        if len(self.tsInfo) < 1:
            print 'No uninstalled build requires'
            sys.exit()
            
        sys.exit(self.doUtilTransaction())
        
    def setupSourceRepos(self):
        # enable the -source repos for enabled primary repos
        archlist = rpmUtils.arch.getArchList() + ['src']    
        for repo in self.repos.listEnabled():
            issource_repo = repo.id.endswith('-source')
            if rhn_source_repos and repo.id.endswith('-source-rpms'):
                issource_repo = True
            if rhn_source_repos and (not repo.id.endswith('-source-rpms') and
                                     repo.id.endswith('-rpms')):
                srcrepo = '%s-source,%s-source-rpms' % (repo.id, repo.id[:-5])
            elif not issource_repo:
                srcrepo = '%s-source' % repo.id
            else:
                # Need to change the arch.
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

    def install_deps(self, deplist):
        errors = set()
        for dep in deplist:
            self.logger.debug(' REQ:  %s' % dep)                
            if dep.startswith("rpmlib("): 
                continue
            instreq = self.returnInstalledPackagesByDep(dep)
            if instreq:
                self.logger.info(' --> Already installed : %s'  % instreq[0])                    
                continue
            try:
                pkg = self.returnPackageByDep(dep)
                self.logger.info(' --> %s' % pkg)
                self.install(pkg)
            except yum.Errors.YumBaseError, e:
                errors.add(exception2msg(e))

        if errors:
            for i in sorted(errors):
                self.logger.error("Error: %s" % i)
            sys.exit(1)

    # go through each of the pkgs, figure out what they are/where they are 
    # if they are not a local package then run
        # Setup source repos
        #self.setupSourceRepos()
    # get all of their deps
    # throw them into a ts
    # run the ts
    
    def get_build_deps(self,opts):
        srcnames = []
        specnames = []
        srpms = []
        specworks = False
        reloadworks = False

        # See if we can use spec files for buildrequires
        if hasattr(rpm, 'spec') and hasattr(rpm.spec, 'sourceHeader'):
            specworks = True
        # See if we can reload rpm configuration
        if hasattr(rpm, 'reloadConfig'):
            reloadworks = True

        for arg in self.cmds:
            if arg.endswith('.src.rpm'):
                try:
                    srpms.append(yum.packages.YumLocalPackage(self.ts, arg))
                except yum.Errors.MiscError, e:
                    self.logger.error("Error: Could not open %s .\nTry" 
                    " running yum-builddep with the --nogpgcheck option." % arg)
                    raise
            elif arg.endswith('.src'):
                srcnames.append(arg)
            elif specworks and arg.endswith('.spec'):
                specnames.append(arg)
            else:
                srcnames.append(arg)

        toActOn = []     
        if srcnames:
            self.setupSourceRepos()
            pkgs = self.pkgSack.returnPackages(patterns=srcnames)
            exact, match, unmatch = yum.packages.parsePackages(pkgs, srcnames, casematch=1)
            srpms += exact + match
            
            if len(unmatch):
                pkgs = self.rpmdb.returnPackages(patterns=unmatch)
                exact, match, unmatch = yum.packages.parsePackages(pkgs, unmatch, casematch=1)
                if len(unmatch):
                    self.logger.error("No such package(s): %s" %
                                      ", ".join(unmatch))
                    sys.exit(1)
                    
        toActOn = []
        for newpkg in srpms:
            toActOn.extend(_best_convert_pkg2srcpkgs(self, opts, newpkg))
        # Get the best matching srpm
        toActOn = self.bestPackagesFromList(toActOn, 'src')

        for srpm in toActOn:
            self.logger.info('Getting requirements for %s' % srpm)
            self.install_deps(srpm.requiresList())
    
        for name in specnames:
            # (re)load rpm config for target if set
            if reloadworks and opts.target:
                rpm.reloadConfig(opts.target)

            try:
                spec = rpm.spec(name)
            except ValueError:
                self.logger.error("Bad spec: %s" % name)
                continue

            # reset default rpm config after each parse to avoid side-effects
            if reloadworks:
                rpm.reloadConfig()

            buildreqs = []
            for d in rpm.ds(spec.sourceHeader, 'requires'):
                buildreqs.append(d.DNEVR()[2:])
                
            self.logger.info('Getting requirements for %s' % name)
            self.install_deps(buildreqs)
            
if __name__ == '__main__':
    setup_locale()
    util = YumBuildDep()
        
       

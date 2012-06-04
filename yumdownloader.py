#!/usr/bin/python 
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
import os
import os.path
sys.path.insert(0,'/usr/share/yum-cli')

import yum
from yum.misc import setup_locale
from yum.packages import parsePackages
from yum.Errors import RepoError
from utils import YumUtilBase

from urlparse import urljoin
from urlgrabber.progress import TextMeter
import shutil

import rpmUtils
import logging

rhn_source_repos = False

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
    if not opts.source or pkg.arch == 'src':
        return [pkg]

    (n,v,r,e,a) = rpmUtils.miscutils.splitFilename(pkg.sourcerpm)
    src = self.pkgSack.searchNevra(name=n, ver=v, rel=r, arch='src')
    if src == []:
        self.logger.error('No source RPM found for %s' % str(pkg))

    return src


class YumDownloader(YumUtilBase):
    NAME = 'yumdownloader'
    VERSION = '1.0'
    USAGE = '"yumdownloader [options] package1 [package2] [package..]'
    
    def __init__(self):
        YumUtilBase.__init__(self,
                             YumDownloader.NAME,
                             YumDownloader.VERSION,
                             YumDownloader.USAGE)
        self.logger = logging.getLogger("yum.verbose.cli.yumdownloader")  
        
        self.localPackages = []
                          
        # Add util commandline options to the yum-cli ones
        self.optparser = self.getOptionParser() 
        self.main()

    def main(self):
        # Add command line option specific to yumdownloader
        self.addCmdOptions()
        # Parse the commandline option and setup the basics.
        try:
            opts = self.doUtilConfigSetup()
        except yum.Errors.RepoError, e:
            self.logger.error(str(e))
            sys.exit(50)
                
        # Check if there is anything to do.
        if len(self.cmds) < 1: 
            print self.optparser.format_help()
            sys.exit(0)

        # make yumdownloader work as non root user.
        if not self.setCacheDir():
            self.logger.error("Error: Could not make cachedir, exiting")
            sys.exit(50)
            
        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup(opts)
        # Do the real action
        self.exit_code = self.downloadPackages(opts)
        
    def setupSourceRepos(self):
        # enable the -source repos for enabled primary repos
        archlist = rpmUtils.arch.getArchList() + ['src']    
        # Ok, we have src and bin repos. What we want to do here is:
        #
        # 1. _enable_ source repos for which the bin repos are enabled.
        # 2. _disable_ the _other_ src repos.
        #
        # ...also we don't want to disable the src repos. for #1 and then
        # re-enable them as then we get annoying messages and call .close() on
        # them losing the primarydb data etc.

        # Get all src repos.
        src_repos = {}
        repos_source = self.repos.findRepos('*-source')
        if rhn_source_repos: # RHN
            repos_source += self.repos.findRepos('*-source-rpms')
        for repo in repos_source:
            src_repos[repo.id] = False

        #  Find the enabled bin repos, and mark their respective *-source repo.
        # as good.
        for repo in self.repos.listEnabled():
            if repo.id not in src_repos:
                srcrepo = '%s-source' % repo.id
                if srcrepo in src_repos:
                    src_repos[srcrepo] = True
                if not rhn_source_repos:
                    continue
                if not repo.id.endswith("-rpms"):
                    continue
                srcrepo = repo.id[:-len('-rpms')] + '-source-rpms'
                if srcrepo in src_repos:
                    src_repos[srcrepo] = True

        # Toggle src repos that are set the wrong way
        for repo in repos_source:
            if     repo.isEnabled() and not src_repos[repo.id]:
                repo.close()
                self.repos.disableRepo(repo.id)
            if not repo.isEnabled() and     src_repos[repo.id]:
                self.logger.info('Enabling %s repository' % repo.id)
                repo.enable()
        
    def downloadPackages(self,opts):
        
        toDownload = []
    
        packages = self.cmds
        for pkg in packages:
            toActOn = []

            if not pkg or pkg[0] != '@':
                pkgnames = [pkg]
            else:
                group_string = pkg[1:]
                pkgnames = set()
                for grp in self.comps.return_groups(group_string):
                    if 'mandatory' in self.conf.group_package_types:
                        pkgnames.update(grp.mandatory_packages)
                    if 'default' in self.conf.group_package_types:
                        pkgnames.update(grp.default_packages)
                    if 'optional' in self.conf.group_package_types:
                        pkgnames.update(grp.optional_packages)
                    if self.conf.enable_group_conditionals:
                        for condreq, cond in grp.conditional_packages.iteritems():
                            if self.isPackageInstalled(cond):
                                pkgnames.add(condreq)

                if not pkgnames:
                    self.logger.error('No packages for group %s' % group_string)
                    continue

            pos = self.pkgSack.returnPackages(patterns=pkgnames)
            exactmatch, matched, unmatched = parsePackages(pos, pkgnames)
            installable = (exactmatch + matched)
            if not installable:
                try:
                    installable = self.returnPackagesByDep(pkg)
                    installable = yum.misc.unique(installable)
                except yum.Errors.YumBaseError, msg:
                    self.logger.error(str(msg))
                    continue

            if not installable: # doing one at a time, apart from groups
                self.logger.error('No Match for argument %s' % pkg)
                continue
            for newpkg in installable:
                toActOn.extend(_best_convert_pkg2srcpkgs(self, opts, newpkg))
            if toActOn:
                pkgGroups = self._groupPackages(toActOn)
                for group in pkgGroups:
                    pkgs = pkgGroups[group]
                    if opts.source:
                        toDownload.extend(self.bestPackagesFromList(pkgs, 'src'))
                    elif opts.archlist:
                        for arch in opts.archlist.split(','):
                            toDownload.extend(self.bestPackagesFromList(pkgs, arch))
                    else:
                        toDownload.extend(self.bestPackagesFromList(pkgs))
                            
        # If the user supplies to --resolve flag, resolve dependencies for
        # all packages
        # note this might require root access because the headers need to be
        # downloaded into the cachedir (is there a way around this)
        if opts.resolve:
            self.doTsSetup()
            # Act as if we were to install the packages in toDownload
            for po in toDownload:
                self.tsInfo.addInstall(po)
                self.localPackages.append(po)
            # Resolve dependencies
            self.resolveDeps()
            # Add newly added packages to the toDownload list
            for pkg in self.tsInfo.getMembers():
                if not pkg in toDownload:
                    toDownload.append(pkg)
        if len(toDownload) == 0:
            self.logger.error('Nothing to download')
            sys.exit(1)

        exit_code = 0
        for pkg in toDownload:
            n,a,e,v,r = pkg.pkgtup
            packages =  self.pkgSack.searchNevra(n,e,v,r,a)
            packages.sort()
            last = None
            for download in packages:
                if download.pkgtup == last :
                    continue
                last = download.pkgtup
                repo = self.repos.getRepo(download.repoid)
                remote = download.returnSimple('relativepath')
                if opts.urls:
                    url = urljoin(repo.urls[0]+'/',remote)
                    self.logger.info('%s' % url)
                    continue
                local = os.path.basename(remote)
                if not os.path.exists(opts.destdir):
                    os.makedirs(opts.destdir)
                local = os.path.join(opts.destdir, local)
                if (os.path.exists(local) and 
                    os.path.getsize(local) == int(download.returnSimple('packagesize'))):
                    self.logger.error("%s already exists and appears to be complete" % local)
                    continue
                # Disable cache otherwise things won't download
                repo.cache = 0
                download.localpath = local # Hack: to set the localpath we want.
                try:
                    checkfunc = (self.verifyPkg, (download, 1), {})
                    path = repo.getPackage(download, checkfunc=checkfunc)
                except IOError, e:
                    self.logger.error("Cannot write to file %s. Error was: %s" % (local, e))
                    exit_code = 2
                    continue
                except RepoError, e:
                    self.logger.error("Could not download/verify pkg %s: %s" % (download, e))
                    exit_code = 2
                    continue
    
                if not os.path.exists(local) or not os.path.samefile(path, local):
                    progress = TextMeter()
                    progress.start(basename=os.path.basename(local),
                                   size=os.stat(path).st_size)
                    shutil.copy2(path, local)
                    progress.end(progress.size)
        return exit_code
                    
    def _groupPackages(self,pkglist):
        pkgGroups = {}
        for po in pkglist:
            na = '%s.%s' % (po.name,po.arch)
            if not na in pkgGroups:
                pkgGroups[na] = [po]
            else:
                pkgGroups[na].append(po)
        return pkgGroups
            
    # sligly modified from the one in YumUtilBase    
    def doUtilYumSetup(self,opts):
        """do a default setup for all the normal/necessary yum components,
           really just a shorthand for testing"""
        try:
            # Setup source repos
            if opts.source:
                self.setupSourceRepos()
            self._getRepos(doSetup = True)
            # if '--source' is used the add src to the archlist
            if opts.source:
                archlist = rpmUtils.arch.getArchList() + ['src']    
            elif opts.archlist:
                archlist = []
                for a in opts.archlist.split(','):
                    archlist.extend(rpmUtils.arch.getArchList(a))
            else:
                archlist = rpmUtils.arch.getArchList()
            self._getSacks(archlist=archlist)
        except yum.Errors.YumBaseError, msg:
            self.logger.critical(str(msg))
            sys.exit(1)

    def addCmdOptions(self):
        # this if for compatibility with old API (utils.py from yum < 3.2.23)
        if hasattr(self,'getOptionGroup'): # check if the group option API is available
            group = self.getOptionGroup()
        else:
            group = self.optparser 
        group.add_option("--destdir", default=".", dest="destdir",
          help='destination directory (defaults to current directory)')
        group.add_option("--urls", default=False, dest="urls", action="store_true",
          help='just list the urls it would download instead of downloading')
        group.add_option("--resolve", default=False, dest="resolve", action="store_true",
          help='resolve dependencies and download required packages')
        group.add_option("--source", default=False, dest="source", action="store_true",
          help='operate on source packages')
        group.add_option("--archlist",
          help="only download packages of certain architecture(s)")        

if __name__ == '__main__':
    setup_locale()
    util = YumDownloader()
    sys.exit(util.exit_code)

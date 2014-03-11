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
from yum.i18n import exception2msg
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
        try:
            self.main()
        except (OSError, IOError), e:
            self.logger.error(exception2msg(e))
            sys.exit(1)

    def main(self):
        # Add command line option specific to yumdownloader
        self.addCmdOptions()
        # Parse the commandline option and setup the basics.
        try:
            opts = self.doUtilConfigSetup()
        except yum.Errors.RepoError, e:
            self.logger.error(exception2msg(e))
            sys.exit(50)
                
        # Check if there is anything to do.
        if len(self.cmds) < 1: 
            print self.optparser.format_help()
            sys.exit(0)

        # make yumdownloader work as non root user.
        if not self.setCacheDir():
            self.logger.error("Error: Could not make cachedir, exiting")
            sys.exit(50)

        # override all pkgdirs
        self.conf.downloaddir = opts.destdir
            
        if opts.source:
            # Setup source repos
            self.arch.archlist.append('src')
            self.setupSourceRepos()

        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup()
        # Do the real action
        self.exit_code = self.downloadPackages(opts)
        
    def setupSourceRepos(self):
        # enable the -source repos for enabled primary repos

        enabled = {}
        for repo in self.repos.findRepos('*'):
            enabled[repo.id] = repo.isEnabled()

        for repo in self.repos.findRepos('*'):
            if repo.id.endswith('-source'):
                primary = repo.id[:-7]
            elif rhn_source_repos and repo.id.endswith('-source-rpms'):
                primary = repo.id[:-12] + '-rpms'
            else:
                continue

            if not repo.isEnabled() and enabled.get(primary):
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
                    self.logger.error(exception2msg(msg))
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
                if pkg.ts_state in ('i', 'u') and pkg.po not in toDownload:
                    toDownload.append(pkg.po)
        if len(toDownload) == 0:
            self.logger.error('Nothing to download')
            sys.exit(1)
        if opts.urls:
            for pkg in toDownload:
                print urljoin(pkg.repo.urls[0], pkg.relativepath)
            return 0

        # set localpaths
        for pkg in toDownload:
            pkg.repo.copy_local = True
            pkg.repo.cache = 0

        # use downloader from YumBase
        exit_code = 0
        probs = self.downloadPkgs(toDownload)
        if probs:
            exit_code = 2
            for key in probs:
                for error in probs[key]:
                    self.logger.error('%s: %s', key, error)
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
          help="only download packages of given and compatible architectures")

if __name__ == '__main__':
    setup_locale()
    util = YumDownloader()
    sys.exit(util.exit_code)

#!/usr/bin/python 
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
from yum.misc import getCacheDir

from cli import *
from utils import YumUtilBase

from urlparse import urljoin
from urlgrabber.progress import TextMeter
import shutil


class YumDownloader(YumUtilBase):
    NAME = 'yumdownloader'
    VERSION = '1.0'
    USAGE = '"usage: yumdownloader [options] package1 [package2] [package..]'
    
    def __init__(self):
        YumUtilBase.__init__(self,
                             YumDownloader.NAME,
                             YumDownloader.VERSION,
                             YumDownloader.USAGE)
        self.logger = logging.getLogger("yum.verbose.cli.yumdownloader")                             
        self.main()

    def main(self):
        # Add util commandline options to the yum-cli ones
        parser = self.getOptionParser() 
        # Add commanself.logger.d line option specific to yumdownloader
        self.addCmdOptions(parser)
        # Parse the commandline option and setup the basics.
        opts = self.doUtilConfigSetup()
        # Check if there is anything to do.
        if len(self.cmds) < 1: 
            parser.print_help()
            sys.exit(0)

        # make yumdownloader work as non root user.
        if self.conf.uid != 0:
            cachedir = getCacheDir()
            if cachedir is None:
                self.logger.error("Error: Could not make cachedir, exiting")
                sys.exit(50)
            self.repos.setCacheDir(cachedir)

        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup()
        # Setup source repos
        if opts.source:
            self.setupSourceRepos()
        # Do the real action
        self.downloadPackages(opts)
        
    def setupSourceRepos(self):
        # enable the -source repos for enabled primary repos
        archlist = rpmUtils.arch.getArchList() + ['src']    
        for repo in self.repos.listEnabled():
            srcrepo = '%s-source' % repo.id
            for r in self.repos.findRepos(srcrepo):
                self.logger.info('Enabling %s repository' % r.id)
                r.enable()
                # Setup the repo
                self._getRepos(thisrepo=r.id,doSetup=True)
                # Setup pkgSack with 'src' in the archlist
                self._getSacks(archlist=archlist,thisrepo=r.id)
        
        
    def downloadPackages(self,opts):
        
        avail = self.pkgSack.returnPackages()
    
        toDownload = []
    
        packages = self.cmds
        for pkg in packages:
            toActOn = []
            exactmatch, matched, unmatched = parsePackages(avail, [pkg])
            installable = yum.misc.unique(exactmatch + matched)
            if len(unmatched) > 0: # if we get back anything in unmatched, it fails
                self.logger.error('No Match for argument %s' % pkg)
                continue
            for newpkg in installable:
                # This is to fix Bug 469
                # If there are matches to the package argument given but there
                # are no source packages, this can be caused because the
                # source rpm this is built from has a different name
                # for example: nscd is built from the glibc source rpm
                # We find this name by parsing the sourcerpm filename
                # (this is ugly but it appears to work)
                # And finding a package with arch src and the same
                # ver and rel as the binary package
                # That should be the source package
                # Note we do not use the epoch to search as the epoch for the
                # source rpm might be different from the binary rpm (see
                # for example mod_ssl)
                if opts.source and newpkg.arch != 'src':
                    name = newpkg.returnSimple('sourcerpm').rsplit('-',2)[0]
                    src = self.pkgSack.searchNevra(name=name, arch = 'src',
                      ver = newpkg.version,
                      rel = newpkg.release
                    )
                    toActOn.extend(src)
                else:
                    toActOn.append(newpkg)
    
            if toActOn:
                if opts.source:
                    toDownload.extend(self.bestPackagesFromList(toActOn, 'src'))
                else:
                    toDownload.extend(self.bestPackagesFromList(toActOn))
        
        # If the user supplies to --resolve flag, resolve dependencies for
        # all packages
        # note this might require root access because the headers need to be
        # downloaded into the cachedir (is there a way around this)
        if opts.resolve:
            self.doTsSetup()
            self.localPackages = []
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
            
        for pkg in toDownload:
            n,a,e,v,r = pkg.pkgtup
            packages =  self.pkgSack.searchNevra(n,e,v,r,a)
            for download in packages:
                repo = self.repos.getRepo(download.repoid)
                remote = download.returnSimple('relativepath')
                if opts.urls:
                    url = urljoin(repo.urls[0],remote)
                    self.logger.info('%s' % url)
                    continue
                local = os.path.basename(remote)
                if not os.path.exists(opts.destdir):
                    os.makedirs(opts.destdir)
                local = os.path.join(opts.destdir, local)
                if (os.path.exists(local) and 
                    str(os.path.getsize(local)) == download.returnSimple('packagesize')):
                    self.logger.error("%s already exists and appears to be complete" % local)
                    continue
                # Disable cache otherwise things won't download
                repo.cache = 0
                download.localpath = local # Hack: to set the localpath we want.
                path = repo.getPackage(download)
    
                if not os.path.exists(local) or not os.path.samefile(path, local):
                    progress = TextMeter()
                    progress.start(basename=os.path.basename(local),
                                   size=os.stat(path).st_size)
                    shutil.copy2(path, local)
                    progress.end(progress.size)
        


    def addCmdOptions(self,parser):
        parser.add_option("--destdir", default=".", dest="destdir",
          help='destination directory (defaults to current directory)')
        parser.add_option("--urls", default=False, dest="urls", action="store_true",
          help='just list the urls it would download instead of downloading')
        parser.add_option("--resolve", default=False, dest="resolve", action="store_true",
          help='resolve dependencies and download required packages')
        parser.add_option("--source", default=False, dest="source", action="store_true",
          help='operate on source packages')
        
if __name__ == '__main__':
    util = YumDownloader()
        
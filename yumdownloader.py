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

import rpmUtils

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
        self.optparser = self.getOptionParser() 
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
            self.optparser.print_help()
            sys.exit(0)

        # make yumdownloader work as non root user.
        if self.conf.uid != 0:
            cachedir = getCacheDir()
            if cachedir is None:
                self.logger.error("Error: Could not make cachedir, exiting")
                sys.exit(50)
            self.repos.setCacheDir(cachedir)

            # Turn off cache
            self.conf.cache = 0
            # make sure the repos know about it, too
            self.repos.setCache(0)
            
        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup(opts)
        # Setup source repos
        if opts.source:
            self.setupSourceRepos()
        # Do the real action
        self.downloadPackages(opts)
        
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
        for repo in self.repos.findRepos('*-source'):
            src_repos[repo.id] = False

        #  Find the enabled bin repos, and mark their respective *-source repo.
        # as good.
        for repo in self.repos.listEnabled():
            if repo.id not in src_repos:
                srcrepo = '%s-source' % repo.id
                if srcrepo in src_repos:
                    src_repos[srcrepo] = True

        # Toggle src repos that are set the wrong way
        for repo in self.repos.findRepos('*-source'):
            if     repo.isEnabled() and not src_repos[repo.id]:
                repo.close()
                self.repos.disableRepo(repo.id)
            if not repo.isEnabled() and     src_repos[repo.id]:
                self.logger.info('Enabling %s repository' % repo.id)
                repo.enable()
                # Setup the repo, without a cache
                repo.setup(0)
                # Setup pkgSack with 'src' in the archlist
                self._getSacks(archlist=archlist, thisrepo=repo.id)
        
        
    def downloadPackages(self,opts):
        
        toDownload = []
    
        packages = self.cmds
        for pkg in packages:
            toActOn = []
            exactmatch, matched, unmatched = parsePackages(self.pkgSack.returnPackages(), [pkg])
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
                    if src == []:
                        self.logger.error('No source RPM found for %s' % str(newpkg))
                        
                    toActOn.extend(src)
                else:
                    toActOn.append(newpkg)
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
        if len(toDownload) == 0:
            self.logger.error('Nothing to download')
            sys.exit(1)
            
        for pkg in toDownload:
            n,a,e,v,r = pkg.pkgtup
            packages =  self.pkgSack.searchNevra(n,e,v,r,a)
            for download in packages:
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
                    path = repo.getPackage(download)
                except IOError, e:
                    self.logger.error("Cannot write to file %s. Error was: %s" % (local, e))
                    continue
                    
    
                if not os.path.exists(local) or not os.path.samefile(path, local):
                    progress = TextMeter()
                    progress.start(basename=os.path.basename(local),
                                   size=os.stat(path).st_size)
                    shutil.copy2(path, local)
                    progress.end(progress.size) 
                    
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
            self._getRepos()
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

    def _removeEnabledSourceRepos(self):
        ''' Disable all enabled *-source repos.'''
        for repo in self.repos.listEnabled():
            if repo.id.endswith('-source'):
                repo.close()
                self.repos.disableRepo(repo.id)
                srcrepo = repo.id

    def addCmdOptions(self):
        self.optparser.add_option("--destdir", default=".", dest="destdir",
          help='destination directory (defaults to current directory)')
        self.optparser.add_option("--urls", default=False, dest="urls", action="store_true",
          help='just list the urls it would download instead of downloading')
        self.optparser.add_option("--resolve", default=False, dest="resolve", action="store_true",
          help='resolve dependencies and download required packages')
        self.optparser.add_option("--source", default=False, dest="source", action="store_true",
          help='operate on source packages')
        self.optparser.add_option("--archlist",
          help="only download packages of certain architecture(s)")        
if __name__ == '__main__':
    import locale
    # This test needs to be before locale.getpreferredencoding() as that
    # does setlocale(LC_CTYPE, "")
    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error, e:
        # default to C locale if we get a failure.
        print >> sys.stderr, 'Failed to set locale, defaulting to C'
        os.environ['LC_ALL'] = 'C'
        locale.setlocale(locale.LC_ALL, 'C')
        
    if True: # not sys.stdout.isatty():
        import codecs
        sys.stdout = codecs.getwriter(locale.getpreferredencoding())(sys.stdout)
        sys.stdout.errors = 'replace'

    util = YumDownloader()
        
        

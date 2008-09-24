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
# Copyright 2007 Seth Vidal

import sys
import os
sys.path.insert(0,'/usr/share/yum-cli/')

import yum
import yum.Errors

from utils import YumUtilBase

import logging
import rpmUtils


class DebugInfoInstall(YumUtilBase):
    NAME = 'debuginfo-install'
    VERSION = '1.0'
    USAGE = """
    debuginfo-install: Install debuginfo packages and their dependencies based on 
                       the name of the non-debug package
    debuginfo-install [options] package1 [package2] [package..]"""
    
    def __init__(self):
        YumUtilBase.__init__(self,
                             DebugInfoInstall.NAME,
                             DebugInfoInstall.VERSION,
                             DebugInfoInstall.USAGE)
        self.logger = logging.getLogger("yum.verbose.cli.debuginfoinstall")
        # Add util commandline options to the yum-cli ones
        self.optparser = self.getOptionParser() 
        self.main()

    def main(self):
        # Parse the commandline option and setup the basics.
        opts = self.doUtilConfigSetup()
        # Check if there is anything to do.
        if len(self.cmds) < 1: 
            self.optparser.print_help()
            sys.exit(0)
        if os.geteuid() != 0:
            print >> sys.stderr, "You must be root to run this command."
            sys.exit(1)
        try:
            self.doLock()
        except yum.Errors.LockError, e:
            self.logger.critical("Another application is holding the yum lock, cannot continue")
            sys.exit(1)
        
        
        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup()
        
        # enable the -debuginfo repos for enabled primary repos
        for repo in self.repos.listEnabled():
            di = '%s-debuginfo' % repo.id
            for r in self.repos.findRepos(di):
                print 'enabling %s' % r.id
                r.enable()
                self.doRepoSetup(thisrepo=r.id)
                #r.setup(self.conf.cache, self.mediagrabber)
        
        self.debugInfo_main()
        self.buildTransaction()
        if len(self.tsInfo) < 1:
            print 'No debuginfo packages available to install'
            self.doUnlock()
            sys.exit()
            
        self.doTransaction()
        self.doUnlock()    
    def di_try_install(self, po):
        di_name = '%s-debuginfo' % po.name
        if self.pkgSack.searchNevra(name=di_name, arch=po.arch):
            test_name = di_name
        else:
            srpm_name = rpmUtils.miscutils.splitFilename(po.sourcerpm)[0] # take the srpmname
            test_name = '%s-debuginfo' % srpm_name
        self.install(name=test_name, arch=po.arch, version=po.version, release=po.release)            
                
        
    def debugInfo_main(self):
        """for each package specified, walk the package's list of deps and install
           all the -debuginfo pkgs that match it and its debuginfo"""
        
        # for each pkg
        # add that debuginfo to the ts
        # look through that pkgs' deps
        # add all the debuginfos for the pkgs providing those deps
        for pkgglob in self.cmds:
            e, m, u = self.rpmdb.matchPackageNames([pkgglob])
            for po in e + m:
                try:
                    self.di_try_install(po)
                except yum.Errors.InstallError, e:
                    self.logger.critical('Could not find debuginfo for main pkg: %s' % po)

                # do each of its deps
                for (n,f,v) in po.requires:
                    if n.startswith('rpmlib'):
                        continue
                    if n.find('.so') != -1:
                        for pkgtup in self.rpmdb.whatProvides(n,f,v):
                            deppo = self.rpmdb.searchPkgTuple(pkgtup)[0]
                            try:
                                self.di_try_install(deppo)
                            except yum.Errors.InstallError, e:
                                self.logger.critical('Could not find debuginfo pkg for dependency package %s' % deppo)
            
        
if __name__ == '__main__':
    import locale
    # This test needs to be before locale.getpreferredencoding() as that
    # does setlocale(LC_CTYPE, "")
    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error, ex:
        # default to C locale if we get a failure.
        print >> sys.stderr, 'Failed to set locale, defaulting to C'
        os.environ['LC_ALL'] = 'C'
        locale.setlocale(locale.LC_ALL, 'C')
        
    if True: # not sys.stdout.isatty():
        import codecs
        sys.stdout = codecs.getwriter(locale.getpreferredencoding())(sys.stdout)
        sys.stdout.errors = 'replace'
    
    util = DebugInfoInstall()

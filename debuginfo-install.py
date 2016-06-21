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
# Copyright 2007 Seth Vidal

import sys
import os
sys.path.insert(0,'/usr/share/yum-cli/')

import yum
import yum.Errors

from utils import YumUtilBase
from yum import _

import logging
import rpmUtils

plugin_autodebuginfo_package_name = "yum-plugin-auto-update-debug-info"

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
        self.optparser = self.getOptionParser()
        opts = self.optparser
        # Add util commandline options to the yum-cli ones
        if hasattr(self, 'getOptionGroup'):
            opts = self.getOptionGroup()
        opts.add_option("", "--no-debuginfo-plugin",
                        action="store_true",
                        help="Turn off automatic installation/update of the yum debuginfo plugin")

        self.done = set()
        try:
            self.main()
        except yum.Errors.YumBaseError, e:
            print e
            sys.exit(1)

    def doUtilConfigSetup(self, *args, **kwargs):
        """ We override this to get our extra option out. """
        opts = YumUtilBase.doUtilConfigSetup(self, *args, **kwargs)
        self.no_debuginfo_plugin = opts.no_debuginfo_plugin
        return opts

    def main(self):
        # Parse the commandline option and setup the basics.
        opts = self.doUtilConfigSetup()
        # Check if there is anything to do.
        if len(self.cmds) < 1: 
            print self.optparser.format_help()
            sys.exit(0)
        if os.geteuid() != 0:
            print >> sys.stderr, "You must be root to run this command."
            sys.exit(1)
        try:
            self.doLock()
        except yum.Errors.LockError, e:
            self.logger.critical("Another application is holding the yum lock, cannot continue")
            sys.exit(1)
        
        # enable the -debuginfo repos for enabled primary repos
        repos = {}
        for repo in self.repos.listEnabled():
            repos[repo.id] = repo
        for repoid in repos:
            if repoid.endswith('-rpms'):
                di = repoid[:-5] + '-debug-rpms'
            else:
                di = '%s-debuginfo' % repoid
            if di in repos:
                continue
            repo = repos[repoid]
            for r in self.repos.findRepos(di):
                self.logger.log(yum.logginglevels.INFO_2, 
                                _('enabling %s') % r.id)
                r.enable()
                # Note: This is shared with auto-update-debuginfo
                for opt in ['repo_gpgcheck', 'gpgcheck', 'cost',
                            'skip_if_unavailable']:
                    if hasattr(r, opt):
                        setattr(r, opt, getattr(repo, opt))

        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup()
        
        self.debugInfo_main()
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
            print 'No debuginfo packages available to install'
            self.doUnlock()
            sys.exit()
            
        sys.exit(self.doUtilTransaction())

    def di_try_install(self, po):
        if po in self.done:
            return
        self.done.add(po)
        if po.name.endswith('-debuginfo'): # Wildcard matches produce this
            return
        di_name = '%s-debuginfo' % po.name
        if self.pkgSack.searchNevra(name=di_name, arch=po.arch):
            test_name = di_name
            ver, rel = po.version, po.release
        else:
            srpm_data = rpmUtils.miscutils.splitFilename(po.sourcerpm) # take the srpmname
            srpm_name, ver, rel = srpm_data[0], srpm_data[1], srpm_data[2]
            test_name = '%s-debuginfo' % srpm_name
        self.install(name=test_name, arch=po.arch, version=ver, release=rel)

    def debugInfo_main(self):
        """for each package specified, walk the package's list of deps and install
           all the -debuginfo pkgs that match it and its debuginfo"""
        
        # for each pkg
        # add that debuginfo to the ts
        # look through that pkgs' deps
        # add all the debuginfos for the pkgs providing those deps
        installonly_added = set()
        for pkgglob in self.cmds:
            e, m, u = self.rpmdb.matchPackageNames([pkgglob])
            for po in sorted(e + m, reverse=True):
                if po.name in installonly_added:
                    continue
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
                if self.allowedMultipleInstalls(po):
                    installonly_added.add(po.name)

        for pkgname in u:
            self.logger.critical('Could not find a package for: %s' % pkgname)

        #  This is kinda hacky, accessing the option from the plugins code
        # but I'm not sure of a better way of doing it
        if not self.no_debuginfo_plugin and self.tsInfo:
            try:
                self.install(pattern=plugin_autodebuginfo_package_name)
            except yum.Errors.InstallError, e:
                self.logger.critical('Could not find auto debuginfo plugin')

        
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

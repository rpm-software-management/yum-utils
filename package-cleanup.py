#!/usr/bin/python
#
# (C) 2005 Gijs Hollestelle, released under the GPL
# Copyright 2009 Red Hat
# Rewritten 2009 - Seth Vidal
#
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
#
#


import sys
sys.path.insert(0,'/usr/share/yum-cli')

from yum.misc import setup_locale
from utils import YumUtilBase
import logging
import os
import re

from rpmUtils import miscutils, arch
from optparse import OptionGroup

def exactlyOne(l):
    return len(filter(None, l)) == 1


class PackageCleanup(YumUtilBase):
    NAME = 'package-cleanup'
    VERSION = '1.0'
    USAGE = """
    package-cleanup: helps find problems in the rpmdb of system and correct them

    usage: package-cleanup --problems or --leaves or --orphans or --oldkernels
    """
    def __init__(self):
        YumUtilBase.__init__(self,
                             PackageCleanup.NAME,
                             PackageCleanup.VERSION,
                             PackageCleanup.USAGE)
        self.logger = logging.getLogger("yum.verbose.cli.packagecleanup")
        # Add util commandline options to the yum-cli ones
        self.optparser = self.getOptionParser()
        self.optparser_grp = self.getOptionGroup()
        self.addCmdOptions()
        self.main()

    def addCmdOptions(self):
        self.optparser_grp.add_option("--problems", default=False, 
                    dest="problems", action="store_true",
                    help='List dependency problems in the local RPM database')
        self.optparser_grp.add_option("--qf", "--queryformat", dest="qf", 
                    action="store",
                    default='%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}',
                    help="Query format to use for output.")
        self.optparser_grp.add_option("--orphans", default=False, 
                    dest="orphans",action="store_true",
                    help='List installed packages which are not available from'\
                         ' currenly configured repositories')

        dupegrp = OptionGroup(self.optparser, 'Duplicate Package Options')
        dupegrp.add_option("--dupes", default=False, 
                    dest="dupes", action="store_true",
                    help='Scan for duplicates in your rpmdb')
        dupegrp.add_option("--cleandupes", default=False, 
                    dest="cleandupes", action="store_true",
                    help='Scan for duplicates in your rpmdb and remove older ')
        dupegrp.add_option("--noscripts", default=False,
                    dest="noscripts", action="store_true",
                    help="disable rpm scriptlets from running when cleaning duplicates")
        self.optparser.add_option_group(dupegrp)
        
        leafgrp = OptionGroup(self.optparser, 'Leaf Node Options')
        leafgrp.add_option("--leaves", default=False, dest="leaves",
                    action="store_true",
                    help='List leaf nodes in the local RPM database')
        leafgrp.add_option("--all", default=False, dest="all_nodes",
                    action="store_true",
                    help='list all packages leaf nodes that do not match'\
                         ' leaf-regex')
        leafgrp.add_option("--leaf-regex", 
                    default="(^(compat-)?lib.+|.*libs?[\d-]*$)",
                    help='A package name that matches this regular expression' \
                         ' (case insensitively) is a leaf')
        leafgrp.add_option("--exclude-devel", default=False, 
                    action="store_true",
                    help='do not list development packages as leaf nodes')
        leafgrp.add_option("--exclude-bin", default=False, 
                    action="store_true",
                    help='do not list packages with files in a bin dirs as'\
                         'leaf nodes')
        self.optparser.add_option_group(leafgrp)        
        
        kernelgrp = OptionGroup(self.optparser, 'Old Kernel Options')
        kernelgrp.add_option("--oldkernels", default=False, 
                    dest="kernels",action="store_true",
                    help="Remove old kernel and kernel-devel packages")
        kernelgrp.add_option("--count",default=2,dest="kernelcount",
                             action="store",
                             help='Number of kernel packages to keep on the '\
                                  'system (default 2)')
        kernelgrp.add_option("--keepdevel", default=False, dest="keepdevel",
                             action="store_true",
                             help='Do not remove kernel-devel packages when '
                                 'removing kernels')
        self.optparser.add_option_group(kernelgrp)
    
    def _find_missing_deps(self, pkgs):
        """find any missing dependencies for any installed package in pkgs"""
        # XXX - move into rpmsack/rpmdb
        
        providers = {} # To speed depsolving, don't recheck deps that have 
                       # already been checked
        problems = []
        for po in pkgs:
            for (req,flags,ver)  in po.requires:
                    
                if req.startswith('rpmlib'): continue # ignore rpmlib deps
                if not providers.has_key((req,flags,ver)):
                    resolve_sack = self.rpmdb.whatProvides(req,flags,ver)
                else:
                    resolve_sack = providers[(req,flags,ver)]
                    
                if len(resolve_sack) < 1:
                    missing = miscutils.formatRequire(req,ver,flags)
                    problems.append((po, "requires %s" % missing))
                                    
                else:
                    # Store the resolve_sack so that we can re-use it if another
                    # package has the same requirement
                    providers[(req,flags,ver)] = resolve_sack
        
        return problems

    def _find_installed_duplicates(self, ignore_kernel=True):
        """find installed duplicate packages returns a dict of 
           pkgname = [[dupe1, dupe2], [dupe3, dupe4]] """
           
        # XXX - this should move to be a method of rpmsack
        
        multipkgs = {}
        singlepkgs = {}
        results = {}
        
        for pkg in self.rpmdb.returnPackages():
            # just skip kernels and everyone is happier
            if ignore_kernel:
                if 'kernel' in pkg.provides_names:
                    continue
                if pkg.name.startswith('kernel'):
                    continue

            name = pkg.name                
            if name in multipkgs or name in singlepkgs:
                continue

            pkgs = self.rpmdb.searchNevra(name=name)
            if len(pkgs)  <= 1:
                continue
            
            for po in pkgs:
                if name not in multipkgs:
                    multipkgs[name] = []
                if name not in singlepkgs:
                    singlepkgs[name] = []
                    
                if arch.isMultiLibArch(arch=po.arch):
                    multipkgs[name].append(po)
                elif po.arch == 'noarch':
                    multipkgs[name].append(po)
                    singlepkgs[name].append(po)
                elif not arch.isMultiLibArch(arch=po.arch):
                    singlepkgs[name].append(po)
                else:
                    print "Warning: neither single nor multi lib arch: %s " % po
            
        for (name, pkglist) in multipkgs.items() + singlepkgs.items():
            if len(pkglist) <= 1:
                continue
                
            if name not in results:
                results[name] = []
            results[name].append(pkglist)
            
            
        return results

    def _remove_old_dupes(self):
        """add older duplicate pkgs to be removed in the transaction"""
        dupedict = self._find_installed_duplicates()

        removedupes = []
        for (name,dupelists) in dupedict.items():
            for dupelist in dupelists:
                dupelist.sort()
                for lowpo in dupelist[0:-1]:
                    removedupes.append(lowpo)

        for po in removedupes:
            self.remove(po)


    def _should_show_leaf(self, po, leaf_regex, exclude_devel, exclude_bin):
        """
        Determine if the given pkg should be displayed as a leaf or not.

        Return True if the pkg should be shown, False if not.
        """
        if po.name == 'gpg-pubkey':
            return False
        name = po.name
        if exclude_devel and name.endswith('devel'):
            return False
        if exclude_bin:
            for file_name in po.filelist:
                if file_name.find('bin') != -1:
                    return False
        if leaf_regex.match(name):
            return True
        return False

    def _get_kernels(self):
        """return a list of all installed kernels, sorted newest to oldest"""

        kernlist =  self.rpmdb.searchProvides(name='kernel')
        kernlist.sort()
        kernlist.reverse()
        return kernlist

    def _get_old_kernel_devel(self, kernels, removelist):
    # List all kernel devel packages that either belong to kernel versions that
    # are no longer installed or to kernel version that are in the removelist
        
        devellist = []
        for po in self.rpmdb.searchProvides(name='kernel-devel'):
            # For all kernel-devel packages see if there is a matching kernel
            # in kernels but not in removelist
            keep = False
            for kernel in kernels:
                if kernel in removelist:
                    continue
                (kname,karch,kepoch,kver,krel) = kernel.pkgtup
                (dname,darch,depoch,dver,drel) = po.pkgtup
                if (karch,kepoch,kver,krel) == (darch,depoch,dver,drel):
                    keep = True
            if not keep:
                devellist.append(po)
        return devellist
        
    def _remove_old_kernels(self, count, keepdevel):
        """Remove old kernels, keep at most count kernels (and always keep the running
         kernel"""

        count = int(count)
        kernels = self._get_kernels()
        runningkernel = os.uname()[2]
        # Vanilla kernels dont have a release, only a version
        if '-' in runningkernel:
            (kver,krel) = runningkernel.split('-')
            if krel.split('.')[-1] == os.uname()[-1]:
                krel = ".".join(krel.split('.')[:-1])
        else:
            kver = runningkernel
            krel = ""
        remove = kernels[count:]
        
        toremove = []
        # Remove running kernel from remove list
        for kernel in remove:
            if kernel.version == kver and krel.startswith(kernel.release):
                print "Not removing kernel %s-%s because it is the running kernel" % (kver,krel)
            else:
                toremove.append(kernel)
        
            
        # Now extend the list with all kernel-devel pacakges that either
        # have no matching kernel installed or belong to a kernel that is to
        # be removed
        if not keepdevel: 
            toremove.extend(self._get_old_kernel_devel(kernels, toremove))

        for po in toremove:
            self.remove(po)


    def main(self):
        opts = self.doUtilConfigSetup()
        if not exactlyOne([opts.problems, opts.dupes, opts.leaves, opts.kernels,
                           opts.orphans, opts.cleandupes]):
            self.optparser.print_help()
            sys.exit(1)

        if self.conf.uid != 0:
            self.setCacheDir()
        
        if opts.problems:
            issues = self._find_missing_deps(self.rpmdb.returnPackages())
            for (pkg, prob) in issues:
                print 'Package %s %s' % (pkg.hdr.sprintf(opts.qf), prob)

            if issues:
                sys.exit(1)
            else:
                print 'No Problems Found'
                sys.exit(0)

        if opts.dupes:
            dupes = self._find_installed_duplicates()
            for name, pkglists in dupes.items():
                for pkglist in pkglists:
                    for pkg in pkglist:
                        print '%s' % pkg.hdr.sprintf(opts.qf)
            sys.exit(0)
        
        if opts.kernels:
            if self.conf.uid != 0:
                print "Error: Cannot remove kernels as a user, must be root"
                sys.exit(1)
            if int(opts.kernelcount) < 1:
                print "Error should keep at least 1 kernel!"
                sys.exit(100)
                
            self._remove_old_kernels(opts.kernelcount, opts.keepdevel)
            self.buildTransaction()
            if len(self.tsInfo) < 1:
                print 'No old kernels to remove'
                sys.exit(0)
            
            sys.exit(self.doUtilTransaction())
            
        
        if opts.leaves:
            leaves = self.rpmdb.returnLeafNodes()
            leaf_reg = re.compile(opts.leaf_regex, re.IGNORECASE)
            for po in sorted(leaves):
                if opts.all_nodes or \
                   self._should_show_leaf(po, leaf_reg, opts.exclude_devel,
                        opts.exclude_bin):
                    print po.hdr.sprintf(opts.qf)
            
            sys.exit(0)

        if opts.orphans:
            if not self.setCacheDir():
                self.logger.error("Error: Could not make cachedir, exiting")
                sys.exit(50)
            
            for po in sorted(self.doPackageLists(pkgnarrow='extras').extras):
                print po.hdr.sprintf(opts.qf)
            sys.exit(0)


        if opts.cleandupes:
            if os.geteuid() != 0:
                print "Error: Cannot remove packages as a user, must be root"
                sys.exit(1)
            if opts.noscripts:
                self.conf.tsflags.append('noscripts')
            self._remove_old_dupes()
            self.buildTransaction()
            if len(self.tsInfo) < 1:
                print 'No duplicates to remove'
                sys.exit(0)
                
            sys.exit(self.doUtilTransaction())

    
if __name__ == '__main__':
    setup_locale()
    util = PackageCleanup()

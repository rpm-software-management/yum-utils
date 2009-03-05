#!/usr/bin/python
#
# (C) 2005 Gijs Hollestelle, released under the GPL
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
# Note: For yum 2.2.X with X <= 1 and yum 2.3.X with X <= 2 --problems
# will report problems with unversioned provides fulfilling versioned
# requires

import yum
import os
import sys
import rpm
import re

from rpmUtils import miscutils, transaction
from optparse import OptionParser
from yum import Errors
from yum.misc import getCacheDir


def initYum(opts):
    debuglevel=2
    errorlevel=2
    if opts.quiet:
        debuglevel=0
        errorlevel=0
    my = yum.YumBase()
    my.doConfigSetup(opts.conffile,init_plugins=not opts.noplugins,
                     debuglevel=debuglevel,errorlevel=errorlevel)
    if opts.orphans:
        # make it work as non root user.
        if my.conf.uid != 0:
            cachedir = getCacheDir()
            if cachedir is None:
                my.logger.error("Error: Could not make cachedir, exiting")
                sys.exit(50)
            my.repos.setCacheDir(cachedir)
            # Turn of cache
            my.conf.cache = 0
        my.doRepoSetup()
    else:
        # Disable all enabled repositories
        for repo in my.repos.listEnabled():
            my.repos.disableRepo(repo.id)

    my.doTsSetup()
    my.doSackSetup()
    my.doRpmDBSetup()
    my.localPackages = []
    return my


def getLocalRequires(my):
    """Get a list of all requirements in the local rpmdb"""
    pkgs = {}
    for po in my.rpmdb.returnPackages():
        tup = po.pkgtup
        header = po.hdr
        requires = zip(
            header[rpm.RPMTAG_REQUIRENAME],
            header[rpm.RPMTAG_REQUIREFLAGS],
            header[rpm.RPMTAG_REQUIREVERSION],
        )
        pkgs[tup] = requires
    return pkgs

def buildProviderList(my, pkgs, reportProblems):
    """Resolve all dependencies in pkgs and build a dictionary of packages
     that provide something for a package other than itself"""

    errors = False
    providers = {} # To speed depsolving, don't recheck deps that have 
                   # already been checked
    provsomething = {}
    for (pkg,reqs) in pkgs.items():
        for (req,flags,ver)  in reqs:
            if ver == '':
                ver = None
            rflags = flags & 15
            if req.startswith('rpmlib'): continue # ignore rpmlib deps
            if not providers.has_key((req,rflags,ver)):
                resolve_sack = my.rpmdb.whatProvides(req,rflags,ver)
            else:
                resolve_sack = providers[(req,rflags,ver)]
                
            if len(resolve_sack) < 1 and reportProblems:
                if not errors:
                    print "Missing dependencies:"
                errors = True
                print "Package %s requires %s" % (pkg[0],
                  miscutils.formatRequire(req,ver,rflags))
            else:
                for rpkg in resolve_sack:
                    # Skip packages that provide something for themselves
                    # as these can still be leaves
                    if rpkg != pkg:
                        provsomething[rpkg] = 1
                # Store the resolve_sack so that we can re-use it if another
                # package has the same requirement
                providers[(req,rflags,ver)] = resolve_sack
    if reportProblems:
        if errors:
            sys.exit(1)
        else:
            print "No problems found"
            sys.exit(0)
    return provsomething

def findDupes(my):
    """takes a yum base object prints out a list of package duplicates.
       These typically happen when an update transaction is left half-completed"""
       
    # iterate rpmdb.pkglist
    # put each package into name. dicts with lists as the po
    # look for any keys with a > 1 length list of pos where the name
    # of the package is not kernel and/or does not provide a kernel-module
    # and the archs is the same or one of the archs is 'noarch'

    pkgdict = {}
    refined = {}
    
    for (n,a,e,v,r) in my.rpmdb.simplePkgList():
        if not pkgdict.has_key((n)):
            pkgdict[(n)] = []
        pkgdict[(n)].append((e,v,r,a))
    
    for (n) in pkgdict.keys():
        # is more than one package with this name ?
        if len(pkgdict[(n)]) > 1:
            archs = set()
            for (e,v,r,a) in pkgdict[(n)]:
                archs.add(a)
            # If all packages with the same name has the same arch, then it is a dupe
            if len(archs) == 1:
                refined[(n)] = pkgdict[(n)]
            # if there is more than one arch, then one must be 'noarch' to be a dupe.
            elif 'noarch' in archs:
                refined[(n)] = pkgdict[(n)]
    
    del pkgdict
    
    return refined
    
def printDupes(my):
    """print out the dupe listing"""
    dupedict = findDupes(my)
    dupes = []    
    for (n) in dupedict.keys():
        for (e,v,r,a) in dupedict[(n)]:
            po = my.getInstalledPackageObject((n,a,e,v,r))
            if po.name.startswith('kernel'):
                continue
            if po.name == 'gpg-pubkey':
                continue
            dupes.append(po)

    for pkg in dupes:
        if pkg.epoch != '0':
            print '%s:%s-%s-%s.%s' % (pkg.epoch, pkg.name, pkg.ver, pkg.rel, pkg.arch)
        else:
            print '%s-%s-%s.%s' % (pkg.name, pkg.ver, pkg.rel, pkg.arch)

def cleanOldDupes(my, confirmed):
    """remove all the older duplicates"""
    dupedict = findDupes(my)
    removedupes = []
    for (n) in dupedict.keys():
        if n.startswith('kernel'):
            continue
        if n.startswith('gpg-pubkey'):
            continue
        (e,v,r,a) = dupedict[(n)][0]
        lowpo = my.getInstalledPackageObject((n,a,e,v,r))

        for (e,v,r,a) in dupedict[(n)][1:]:
            po = my.getInstalledPackageObject((n,a,e,v,r))
            if po.EVR < lowpo.EVR:
                lowpo = po
                
        removedupes.append(lowpo)
    if len(removedupes) == 0:
        print "No dupes to clean"
        sys.exit(0)
        
    print "I will remove the following old duplicate packages:"
    for po in removedupes:
        print "%s" % po

    if not confirmed:
        if not userconfirm():
            sys.exit(0)

    for po in removedupes:
        my.remove(po)

    # Now perform the action transaction
    my.populateTs()
    my.ts.check()
    my.ts.order()
    my.ts.run(progress,'')
                 


def _shouldShowLeaf(my, pkg, leaf_regex, exclude_devel, exclude_bin):
    """
    Determine if the given pkg should be displayed as a leaf or not.

    Return True if the pkg should be shown, False if not.
    """
    if pkg[0] == 'gpg-pubkey':
        return False
    pos = my.rpmdb.searchNevra(name=pkg[0], epoch=str(pkg[2]), ver=pkg[3],
            rel=pkg[4], arch=pkg[1])
    # This should give us an exact match
    assert len(pos) == 1
    po = pos[0]
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

def listLeaves(my, all_nodes, leaf_regex, exclude_devel, exclude_bin):
    """return a packagtuple of any installed packages that
       are not required by any other package on the system"""
    ts = transaction.initReadOnlyTransaction()
    leaves = ts.returnLeafNodes()
    for pkg in leaves:
        name = pkg[0]
        if all_nodes or _shouldShowLeaf(my, pkg, leaf_regex, exclude_devel,
                exclude_bin):
            print "%s-%s-%s.%s" % (pkg[0],pkg[3],pkg[4],pkg[1])

def listOrphans(my):
    """ This is "yum list extras". """
    avail = my.pkgSack.simplePkgList()
    avail = set(avail)
    for po in sorted(my.rpmdb.returnPackages()):
        (n,a,e,v,r) = po.pkgtup
        if n == "gpg-pubkey": # Not needed as of at least 3.2.19, but meh
            continue

        if po.pkgtup not in avail:
            print "%s-%s-%s.%s" % (n, v, r, a)

def getKernels(my):
    """return a list of all installed kernels, sorted newest to oldest"""
    kernlist = []
    for po in my.rpmdb.searchNevra(name='kernel'):
        kernlist.append(po.pkgtup)
    kernlist.sort(sortPackages)
    kernlist.reverse()
    return kernlist

# List all kernel devel packages that either belong to kernel versions that
# are no longer installed or to kernel version that are in the removelist
def getOldKernelDevel(my,kernels,removelist):
    devellist = []
    for po in my.rpmdb.searchNevra(name='kernel-devel'):
        # For all kernel-devel packages see if there is a matching kernel
        # in kernels but not in removelist
        tup = po.pkgtup
        keep = False
        for kernel in kernels:
            if kernel in removelist:
                continue
            (kname,karch,kepoch,kver,krel) = kernel
            (dname,darch,depoch,dver,drel) = tup
            if (karch,kepoch,kver,krel) == (darch,depoch,dver,drel):
                keep = True
        if not keep:
            devellist.append(tup)
    return devellist

    
def sortPackages(pkg1,pkg2):
    """sort pkgtuples by evr"""
    return miscutils.compareEVR((pkg1[2:]),(pkg2[2:]))

def progress(what, bytes, total, h, user):
    pass
    #if what == rpm.RPMCALLBACK_UNINST_STOP:
    #    print "Removing: %s" % h 

def userconfirm():
    """gets a yes or no from the user, defaults to No"""
    while True:            
        choice = raw_input('Is this ok [y/N]: ')
        choice = choice.lower()
        if len(choice) == 0 or choice[0] in ['y', 'n']:
            break

    if len(choice) == 0 or choice[0] != 'y':
        return False
    else:            
        return True
    
def removeKernels(my, count, confirmed, keepdevel):
    """Remove old kernels, keep at most count kernels (and always keep the running
     kernel"""

    count = int(count)
    if count < 1:
        print "Error should keep at least 1 kernel!"
        sys.exit(100)
    kernels = getKernels(my)
    runningkernel = os.uname()[2]
    (kver,krel) = runningkernel.split('-')
    
    remove = kernels[count:]
    toremove = []
    
    # Remove running kernel from remove list
    for kernel in remove:
        (n,a,e,v,r) = kernel
        if (v == kver and r == krel):
            print "Not removing kernel %s-%s because it is the running kernel" % (kver,krel)
        else:
            toremove.append(kernel)
    
    if len(kernels) - len(toremove) < 1:
        print "Error all kernel rpms are set to be removed"
        sys.exit(100)
        
    # Now extend the list with all kernel-devel pacakges that either
    # have no matching kernel installed or belong to a kernel that is to
    # be removed
    if not keepdevel: 
        toremove.extend(getOldKernelDevel(my,kernels,toremove))

    if len(toremove) < 1:
        print "No kernel related packages to remove"
        return

    print "I will remove the following %s kernel related packages:" % len(toremove)
    for kernel in toremove:
        (n,a,e,v,r) = kernel
        print "%s-%s-%s" % (n,v,r) 

    if not confirmed:
        if not userconfirm():
            sys.exit(0)

    for kernel in toremove:
        po = my.rpmdb.searchPkgTuple(kernel)[0]
        my.tsInfo.addErase(po)

    # Now perform the action transaction
    my.populateTs()
    my.ts.check()
    my.ts.order()
    my.ts.run(progress,'')
    
# Returns True if exactly one value in the list evaluates to True
def exactlyOne(l):
    return len(filter(None, l)) == 1
    
# Parse command line options
def parseArgs():
    parser = OptionParser()
    parser.add_option("--problems", default=False, dest="problems", action="store_true",
      help='List dependency problems in the local RPM database')

    # Leaf listing options
    parser.add_option("--leaves", default=False, dest="leaves",action="store_true",
      help='List leaf nodes in the local RPM database')
    parser.add_option("--all", default=False, dest="all_nodes",action="store_true",
      help='When listing leaf nodes also list leaf nodes that do not match leaf-regex')
    parser.add_option("--leaf-regex", default="(^(compat-)?lib.+|.*libs?[\d-]*$)",
      help='A package name that matches this regular expression (case insensitively) is a leaf')

    parser.add_option("--exclude-devel", default=False, action="store_true",
      help='When listing leaf nodes do not list development packages')
    parser.add_option("--exclude-bin", default=False, action="store_true",
      help='When listing leaf nodes do not list packages with files in bin dirs')

    parser.add_option("--orphans", default=False, dest="orphans",action="store_true",
      help='List installed packages which are not available from currenly configured repositories')
    parser.add_option("--noplugins", default=False, dest="noplugins",action="store_true",
      help='Turn plugin support off')
    parser.add_option("-q", "--quiet", default=False, dest="quiet",action="store_true",
      help='Print out nothing unecessary')
    parser.add_option("-y", default=False, dest="confirmed",action="store_true",
      help='Agree to anything asked')
    parser.add_option("-d", "--dupes", default=False, dest="dupes", action="store_true",
      help='Scan for duplicates in your rpmdb')
    parser.add_option("--cleandupes", default=False, dest="cleandupes", action="store_true",
      help='Scan for duplicates in your rpmdb and cleans out the older versions')    
    parser.add_option("--oldkernels", default=False, dest="kernels",action="store_true",
      help="Remove old kernel and kernel-devel packages")
    parser.add_option("--count",default=2,dest="kernelcount",action="store",
      help="Number of kernel packages to keep on the system (default 2)")
    parser.add_option("--keepdevel",default=False,dest="keepdevel",action="store_true",
      help="Do not remove kernel-devel packages when removing kernels")
    parser.add_option("-c", dest="conffile", action="store",
                default='/etc/yum.conf', help="config file location")

    (opts, args) = parser.parse_args()
    if not exactlyOne((opts.problems,opts.leaves,opts.kernels,opts.orphans, opts.dupes, opts.cleandupes)): 
        parser.print_help()
        print "Please specify either --problems, --leaves, --orphans or --oldkernels"
        sys.exit(0)
    return (opts, args)
    
def main():
    (opts, args) = parseArgs()
    if not opts.quiet:
        print "Setting up yum"
    my = initYum(opts)
    
    if (opts.kernels):
        if os.geteuid() != 0:
            print "Error: Cannot remove kernels as a user, must be root"
            sys.exit(1)
        removeKernels(my, opts.kernelcount, opts.confirmed, opts.keepdevel)
        sys.exit(0)
    
    if (opts.leaves):
        listLeaves(my, opts.all_nodes, re.compile(opts.leaf_regex, re.IGNORECASE),
                opts.exclude_devel, opts.exclude_bin)
        sys.exit(0)

    if (opts.orphans):
        listOrphans(my)
        sys.exit(0)

    if opts.dupes:
        printDupes(my)
        sys.exit(0)

    if opts.cleandupes:
        if os.geteuid() != 0:
            print "Error: Cannot remove packages as a user, must be root"
            sys.exit(1)
    
        cleanOldDupes(my, opts.confirmed)
        sys.exit(0)
            
    if not opts.quiet:
        print "Reading local RPM database"
    pkgs = getLocalRequires(my)
    if not opts.quiet:
        print "Processing all local requires"
    provsomething = buildProviderList(my,pkgs,opts.problems)
    
if __name__ == '__main__':
    main()

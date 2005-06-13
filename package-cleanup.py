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
#
# TODO find a nicer way to see if a package is a lib (tweakeable via command
# line options, i.e. --exclude-devel)
#

import yum
import os
import sys
import rpm
from rpmUtils import miscutils, transaction
from yum.logger import Logger
from optparse import OptionParser
from yum.packages import YumInstalledPackage


def initYum():
    my = yum.YumBase()
    my.doConfigSetup()
    my.log = Logger(threshold=my.conf.getConfigOption('debuglevel'), 
    file_object =sys.stdout)
    # Disable all enabled repositories
    for repo in my.repos.listEnabled():
        my.repos.disableRepo(repo.id)

    my.doTsSetup()
    my.doSackSetup()
    my.doRpmDBSetup()
    my.localPackages = []
    return my

# Get a list of all requirements in the local rpmdb
def getLocalRequires(my):
    pkgs = {}
    for header in my.rpmdb.getHdrList():
        tup = my.rpmdb._hdr2pkgTuple(header)
        requires = zip(
            header[rpm.RPMTAG_REQUIRENAME],
            header[rpm.RPMTAG_REQUIREFLAGS],
            header[rpm.RPMTAG_REQUIREVERSION],
        )
        pkgs[tup] = requires
    return pkgs

# Resolve all dependencies in pkgs and build a dictionary of packages
# that provide something for a package other than itself
def buildProviderList(my,pkgs,reportProblems):
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
            
            if (not providers.has_key((req,rflags,ver))):
                resolve_sack = my.rpmdb.whatProvides(req,rflags,ver)
            else:
                resolve_sack = providers[(req,rflags,ver)]
                
            if len(resolve_sack) < 1 and reportProblems:
                if (not errors):
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
    if (not errors and reportProblems):
        print "No problems found"
    return provsomething


def listLeaves(all):
    """return a packagtuple of any installed packages that
       are not required by any other package on the system"""
    ts = transaction.initReadOnlyTransaction()
    leaves = ts.returnLeafNodes()
    for pkg in leaves:
        name=pkg[0]
        if name.startswith('lib') or all:
            print "%s-%s-%s.%s" % (pkg[0],pkg[3],pkg[4],pkg[1])


def getKernels(my):
    """return a list of all installed kernels, sorted newest to oldest"""
    kernlist = []
    for tup in my.rpmdb.returnTupleByKeyword(name='kernel'):
        kernlist.append(tup)
    kernlist.sort(sortPackages)
    kernlist.reverse()
    return kernlist


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
    
# Remove old kernels, keep at most count kernels (and always keep the running
# kernel)
def removeKernels(my, count):
    count = int(count)
    if count < 1:
        print "Error should keep at least 1 kernel!"
        sys.exit(100)
    kernels = getKernels(my)
    runningkernel = os.uname()[2]
    (kver,krel) = runningkernel.split('-')
    if len(kernels) < count:
        print "There are only %s kernels installed of maximum %s kernels, nothing to be done" % (len(kernels),count)
        return
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
    if len(toremove) < 1:
        print "No kernels to remove"
        return
    
    print "I will remove the following %s kernel(s):" % len(toremove)
    for kernel in toremove:
        (n,a,e,v,r) = kernel
        print "%s-%s" % (v,r) 

    if (not userconfirm()):
        sys.exit(0)

    for kernel in toremove:
        hdr = my.rpmdb.returnHeaderByTuple(kernel)[0]
        po = YumInstalledPackage(hdr)
        my.tsInfo.addErase(po)

    # Now perform the action transaction
    my.populateTs()
    my.ts.check()
    my.ts.order()
    my.ts.run(progress,'')
    
# Parse command line options
def parseArgs():
    parser = OptionParser()
    parser.add_option("--problems", default=False, dest="problems", action="store_true",
      help='List dependency problems in the local RPM database')
    parser.add_option("--leaves", default=False, dest="leaves",action="store_true",
      help='List leaf nodes in the local RPM database')
    parser.add_option("--all", default=False, dest="all",action="store_true",
      help='When listing leaf nodes also list leaf nodes that are not libraries')
    parser.add_option("-q", "--quiet", default=False, dest="quiet",action="store_true",
      help='Print out nothing unecessary')
    parser.add_option("--oldkernels", default=False, dest="kernels",action="store_true",
      help="Remove old kernels")
    parser.add_option("--count",default=2,dest="kernelcount",action="store",
      help="Number of kernels to keep on the system (default 2)")
    (opts, args) = parser.parse_args()
    if not (opts.problems or opts.leaves or opts.kernels) or (opts.problems and opts.leaves):
        parser.print_help()
        print "Please specify either --problems or --leaves"
        sys.exit(0)
    return (opts, args)
    
def main():
    (opts, args) = parseArgs()
    if not opts.quiet:
        print "Setting up yum"
    my = initYum()
    
    if (opts.kernels):
        removeKernels(my, opts.kernelcount)
        sys.exit(0)
    
    if (opts.leaves):
        listLeaves(opts.all)
        sys.exit(0)

    if not opts.quiet:
        print "Reading local RPM database"
    pkgs = getLocalRequires(my)
    if not opts.quiet:
        print "Processing all local requires"
    provsomething = buildProviderList(my,pkgs,opts.problems)
    
if __name__ == '__main__':
    main()

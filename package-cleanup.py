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
import sys
import rpm
from rpmUtils import miscutils
from yum.logger import Logger
from optparse import OptionParser

def initYum():
    my = yum.YumBase()
    my.doConfigSetup()
    my.log = Logger(threshold=my.conf.getConfigOption('debuglevel'), 
    file_object =sys.stdout)
    # Disable all enabled repositories
    for repo in my.repos.listEnabled():
        my.repos.disableRepo(repo.id)

    print "Setting up yum"
    my.doTsSetup()
    my.doSackSetup()
    my.doRpmDBSetup()
    return my

# Get a list of all requirements in the local rpmdb
def getLocalRequires(my):
    pkgs = {}
    for tup in my.rpmdb.getPkgList():
        headerlist = my.rpmdb.returnHeaderByTuple(tup)
        for header in headerlist:
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

# Parse command line options
def parseArgs():
    parser = OptionParser()
    parser.add_option("--problems", default=False, dest="problems", action="store_true",
      help='List dependency problems in the local RPM database')
    parser.add_option("--leaves", default=False, dest="leaves",action="store_true",
      help='List leaf nodes in the local RPM database')
    parser.add_option("--all", default=False, dest="all",action="store_true",
      help='When listing leaf nodes also list leaf nodes that are not libraries')
    (opts, args) = parser.parse_args()
    if not (opts.problems or opts.leaves) or (opts.problems and opts.leaves):
        parser.print_help()
        print "Please specify either --problems or --leaves"
        sys.exit(0)
    return (opts, args)

def listLeaves(pkgs,provsomething,all):
    # Any installed packages that are not in provsomething don't provide 
    # anything required by the rest of the system and are therefore leave nodes
    for pkg in pkgs:
        if (not provsomething.has_key(pkg)):
            name = pkg[0]
            if name in ['gpg-pubkey']:
                continue
            if name.find('lib') == 0 or all:
                print "%s-%s-%s.%s" % (pkg[0],pkg[3],pkg[4],pkg[1])

def main():
    (opts, args) = parseArgs()
    my = initYum()
    print "Reading local RPM database"
    pkgs = getLocalRequires(my)
    print "Processing all local requires"
    provsomething = buildProviderList(my,pkgs,opts.problems)
    if (opts.leaves):
        listLeaves(pkgs,provsomething,opts.all)
    
    
if __name__ == '__main__':
    main()

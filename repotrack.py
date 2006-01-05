#!/usr/bin/python -tt
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
# (c) 2005 seth vidal skvidal at phy.duke.edu


# specify list of repos or default in yum.conf
# specify list of pkgs - default to *
# download latest set + any deps to a specified dir
# alternatively:
# repomanage repo
# createrepo repo
# repoview repo
# email some address the list of new/updated packages.

# need to keep state of current repo to know what's 'new' and when to download things
# arch should be specified or default to system arch.

import os
import sys
import time

import yum
import yum.Errors
from yum.misc import getCacheDir
from yum.constants import *
from yum.packages import parsePackages

output_dir = '/tmp/repotrack_dir'
user_pkg_list = ['mplayer', 'mplayerplug-in', 'yum']
enabled_repos = ['livna', 'livna-testing']

class RepoTrack(yum.YumBase):
    def __init__(self, config = "/etc/yum.conf"):
        yum.YumBase.__init__(self)


    def findDeps(self, pkg_object_list):
        """Return the dependencies for a given package, as well
           possible solutions for those dependencies.
           
           Returns the deps as a dict  of:
             packageobject = [reqs] = [list of satisfying pkgs]"""
        
        results = {}
    
        for pkg in pkg_object_list:
            results[pkg] = {} 
            reqs = pkg.returnPrco('requires');
            reqs.sort()
            pkgresults = results[pkg] # shorthand so we don't have to do the
                                      # double bracket thing
            
            for req in reqs:
                (r,f,v) = req
                if r.startswith('rpmlib('):
                    continue
                
                satisfiers = []
    
                for po in self.whatProvides(r, f, v):
                    satisfiers.append(po)
    
                pkgresults[req] = satisfiers
        
        return results
    

def more_to_check(unprocessed_pkgs):
    for pkg in unprocessed_pkgs.keys():
        if unprocessed_pkgs[pkg] is not None:
            return True
    
    return False


def main():
# setup yum basics
# read in repo info
# find all its deps using findDeps()
# set the download path to output_dir
# download and gpg/sha checksum them
# output list of things that actually got downloaded.


# arguments to take: arch, repos, package names to track, yum config file,
#                    download or list urls


    my = RepoTrack()
    my.doConfigSetup()
    
    # do the happy tmpdir thing if we're not root
    if os.geteuid() != 0:
        cachedir = getCacheDir()
        if cachedir is None:
            print "Error: Could not make cachedir, exiting"
            sys.exit(50)
            
        my.repos.setCacheDir(cachedir)

    for repo in my.repos.repos.values():
        if repo.id not in enabled_repos:
            repo.disable()
        else:
            repo.enable()
    
    my.doRepoSetup()    
    my.doSackSetup()
    
    unprocessed_pkgs = {}
    final_pkgs = {}
    user_po_list = []
    pkg_list = []
    
    avail = my.pkgSack.returnPackages()
    for item in user_pkg_list:
        print item
        exactmatch, matched, unmatched = parsePackages(avail, [item])
        pkg_list.extend(my.bestPackagesFromList(exactmatch+matched))
    
    for po in pkg_list:
        unprocessed_pkgs[po.pkgtup] = po
    

    while more_to_check(unprocessed_pkgs):
    
        for pkgtup in unprocessed_pkgs.keys():
            if unprocessed_pkgs[pkgtup] is None:
                continue

            po = unprocessed_pkgs[pkgtup]
            final_pkgs[po.pkgtup] = po
            
            deps_dict = my.findDeps([ po ])
            unprocessed_pkgs[po.pkgtup] = None
            for deps_po in deps_dict.keys():
                for req in deps_dict[deps_po].keys():
                    best_res = my.bestPackagesFromList(deps_dict[deps_po][req])
                    for res in best_res:
                        if res is not None:
                            if not unprocessed_pkgs.has_key(res.pkgtup):
                                unprocessed_pkgs[res.pkgtup] = res
        
        for pkgtup in unprocessed_pkgs.keys():
            if unprocessed_pkgs[pkgtup] is not None:
                print unprocessed_pkgs[pkgtup]

        
    for po in final_pkgs.values():
        print po

if __name__ == "__main__":
    main()
    

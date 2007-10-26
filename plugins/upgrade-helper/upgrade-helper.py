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
# Copyright 2007 Red Hat, Inc
# Written by Seth Vidal

# upgrade-helper plugin
# cleans out orphans and impossible-to-update/obsolete-away pkgs

# download list of stuff to kill from each repo, if there
# parse it and load it into memory
#  - make sure that any pkgspec matching: a lot of things *? or * or . or what not
#    will be ignored


#format of the file is:
#<cleanup>
#  <removespec pkgmatch="zsh.i386" on_arch="x86_64"/>
#  <removespec pkgmatch="zvbi"/>
#</cleanup>

# for all the ones for anything in your arch
#  if something is installed matching it, then add it to the TS to be removed
# do all this only if:
   # running as root
   # the command being run is 'update' or 'install'  (or performing those functions somehow)

from yum.plugins import TYPE_CORE
from yum.constants import *
from yum import config
import rpmUtils.arch
from yum.repoMDObject import ns_cleanup

import gzip

try:
    from xml.etree import cElementTree
except ImportError:
    import cElementTree
iterparse = cElementTree.iterparse


requires_api_version = '2.5'
plugin_type = (TYPE_CORE,)
myarch = rpmUtils.arch.getBaseArch()

def parse_xml(xmlfile):
    """parse the xml file and hand back the contents in a usable form"""
    # store results in a dict of on_arch = list_of_pkgs
    results = {}
    results[myarch] = []
    
    xfo = gzip.open(xmlfile, 'rt')
    parser = iterparse(xfo)
    for ev, elem in parser:
        for child in elem:
            child_name = ns_cleanup(child.tag)
            thisarch = myarch
            if child_name == 'removespec':
                if child.attrib.has_key('on_arch'):
                    thisarch = child.attrib.get('on_arch')
                if child.attrib.has_key('pkgmatch'):
                    thismatch = child.attrib.get('pkgmatch')
                    if results.has_key(thisarch):
                        if thismatch not in results[thisarch]:
                            results[thisarch].append(thismatch)
                        else:
                            results[thisarch] = [thismatch]
    return results
    
def stuff_to_remove(repos):
    toremove = []
    
    # for repo in my repos
    #  grab the cleanup file
    #  parse it
    #  merge all the results for $myarch together
    #  return them as the toremove list

    for repo in repos.listEnabled():
        if repo.repoXML.repoData.has_key('cleanup'):
            trf = repo.retrieveMD('cleanup')
            tr_dict = parse_xml(trf)
            # prune out things like *, ?, *.*, *.*.*.*.*
            # etc
            badmatches = ['*', '?', '*.*', 'glibc', 'kernel', 'yum', 'rpm']
            
            for pm in tr_dict[myarch]:
                if pm in badmatches:
                    continue
                # other tests here?
                toremove.append(pm)
    
    return toremove

def preresolve_hook(conduit):
    """add all of these into the ts to be removed"""
    ts = conduit.getTsInfo()
    # only run it if we're installing/updating something, don't do it if 
    # we're removing only
    runme = False
    for mbr in ts.getMembers():
        if mbr.output_state in TS_INSTALL_STATES:
            runme = True
            break
    if runme:
        rpmdb = conduit.getRpmDB()
        for pkgglob in stuff_to_remove(conduit.getRepos()):
            for po in rpmdb.matchPackageNames(pkgglob, casematch=True):
                conduit.info(1, "Setting %s to be removed due to repository metadata in cleanup plugin" % po)
                ts.addErase(po)


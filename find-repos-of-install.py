#!/usr/bin/python -tt
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
# copyright 2008 red hat, inc

import sys
import os
import os.path

from optparse import OptionParser

import yum

my = yum.YumBase()
my.conf.showdupesfromrepos = 1

if True:
    parser = OptionParser(version = "find-repos-of-installed version 0.1")

    parser.add_option("--repoid", action="append",
                      help="specify repoids to query, can be specified multiple times (default is all enabled)")

    parser.add_option("--enablerepo", action="append", dest="enablerepos",
                      help="specify additional repoids to query, can be specified multiple times")
    parser.add_option("--disablerepo", action="append", dest="disablerepos",
                      help="specify repoids to disable, can be specified multiple times")                      
    parser.add_option("--repofrompath", action="append",
                      help="specify repoid & paths of additional repositories - unique repoid and complete path required, can be specified multiple times. Example. --repofrompath=myrepo,/path/to/repo")

    parser.add_option("-C", "--cache", action="store_true",
                      help="run from cache only")
    parser.add_option("--tempcache", action="store_true",
                      help="use private cache (default when used as non-root)")
    parser.add_option("--sync2yumdb", action="store_true",
                      help="sync anything that is found to the yumdb, if available")


    (opts, args) = parser.parse_args()

    if not my.setCacheDir(opts.tempcache):
        my.logger.error("Error: Could not make cachedir, exiting")
        sys.exit(50)

    if opts.cache:
        my.conf.cache = True
        my.logger.info('Running from cache, results might be incomplete.')

    if opts.repofrompath:
        # setup the fake repos
        for repo in opts.repofrompath:
            repoid,repopath = tuple(repo.split(','))
            if repopath[0] == '/':
                baseurl = 'file://' + repopath
            else:
                baseurl = repopath
                
            repopath = os.path.normpath(repopath)
            newrepo = yum.yumRepo.YumRepository(repoid)
            newrepo.name = repopath
            newrepo.baseurl = baseurl
            newrepo.basecachedir = my.conf.cachedir
            newrepo.metadata_expire = 0
            newrepo.timestamp_check = False
            my.repos.add(newrepo)
            my.repos.enableRepo(newrepo.id)
            my.logger.info( "Added %s repo from %s" % (repoid,repopath))

    if opts.repoid:
        for repo in my.repos.findRepos('*'):
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                repo.enable()
    if opts.disablerepos:
        for repo_match in opts.disablerepos:
            for repo in my.repos.findRepos(repo_match):
                repo.disable()

    if opts.enablerepos:    
        for repo_match in opts.enablerepos:
            for repo in my.repos.findRepos(repo_match):
                repo.enable()



if len(args) >= 1:
    pkgs = my.rpmdb.returnPackages(patterns=sys.argv[1:], ignore_case=True)
else:
    pkgs = my.rpmdb

for ipkg in sorted(pkgs):
    if 'from_repo' in ipkg.yumdb_info:
        print '%s from repo %s' % (ipkg, ipkg.yumdb_info.from_repo)
        continue

    apkgs = my.pkgSack.searchPkgTuple(ipkg.pkgtup)
    if len(apkgs) < 1:
        print "Error: %s not found in any repository" % ipkg
    else:
        apkg = apkgs[0]
        if opts.sync2yumdb: # and hasattr(ipkg, 'yumdb_info'): for compat. ?
            ipkg.yumdb_info.from_repo = apkg.repoid
        print '%s from repo %s' % (ipkg, apkg.repoid)
        
    

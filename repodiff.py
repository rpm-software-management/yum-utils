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
# (c) 2007 Red Hat. Written by skvidal@fedoraproject.org

import yum
import rpmUtils
import sys
import time

class DiffYum(yum.YumBase):
    def __init__(self):
        yum.YumBase.__init__(self)

    def shutdown_all_other_repos(self):
        # disable all the other repos
        self.repos.disableRepo('*')

        
    def setup_repo(self, repoid, baseurl, srcrepo=False):
        # make our new repo obj
        newrepo = yum.yumRepo.YumRepository(repoid)
        newrepo.name = repoid
        newrepo.baseurl = [baseurl]
        newrepo.basecachedir = '/tmp/tfoo'
        # add our new repo
        self.repos.add(newrepo)        
        # enable that repo
        self.repos.enableRepo(repoid)
        # setup the repo dirs/etc
        self.doRepoSetup(thisrepo=repoid)
        if srcrepo:
            archlist = rpmUtils.arch.getArchList() + ['src']    
            self._getSacks(archlist=archlist, thisrepo=repoid)

    def diff(self):
        add = []
        remove = []        
        modified = []
        for pkg in self.pkgSack.returnPackages(repoid='new'):
            tot = self.pkgSack.searchNevra(name=pkg.name)
            if len(tot) == 1: # it's only in new
                add.append(pkg)
            if len(tot) > 1:
                for oldpkg in tot:
                    if pkg  != oldpkg:
                        modified.append((pkg, oldpkg))
        for pkg in self.pkgSack.returnPackages(repoid='old'):
            tot = self.pkgSack.searchNevra(name=pkg.name)
            if len(tot) == 1: # it's only in old       
                remove.append(pkg)
        
        return add, remove, modified


def main(args):
    if len(args) != 2:
        print "\nUsage:\n     repodiff old_repo_baseurl new_repo_baseurl\n"
        sys.exit(1)
        
    my = DiffYum()
    my.shutdown_all_other_repos()
    print 'setting up repos'
    my.setup_repo('old', args[0], srcrepo=True)
    my.setup_repo('new', args[1], srcrepo=True)
    print 'performing the diff'
    add, rem, mod = my.diff()
  

               
    if add:
        for pkg in add:
            print 'New package %s' % pkg.name
            print '        %s' % pkg.summary
    if rem:
        for pkg in rem:
            print 'Removed package %s' % pkg.name
    if mod:
        print 'Updated Packages:\n'
        for (pkg, oldpkg) in mod:
            msg = '%s-%s-%s' % (pkg.name, pkg.ver, pkg.rel)
            dashes = '-' * len(msg) 
            msg += '\n%s\n' % dashes
            # get newest clog time from the oldpkg
            # for any newer clog in pkg
            # print it
            oldlogs = oldpkg.changelog
            oldlogs.sort()
            oldlogs.reverse()
            oldtime = oldlogs[0][0]
            for (t, author, content) in  pkg.changelog:
                  if t > oldtime:
                      msg += "* %s %s\n%s\n" % (time.ctime(int(t)), author, content)
            print msg



if __name__ == "__main__":
    main(sys.argv[1:])
    

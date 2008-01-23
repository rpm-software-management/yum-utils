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

from optparse import OptionParser

class DiffYum(yum.YumBase):
    def __init__(self):
        yum.YumBase.__init__(self)
        self.dy_repos = {'old':[], 'new':[]}
        self.dy_basecachedir = yum.misc.getCacheDir()
        
    def dy_shutdown_all_other_repos(self):
        # disable all the other repos
        self.repos.disableRepo('*')

        
    def dy_setup_repo(self, repotype, baseurl):
        repoid = repotype + str (len(self.dy_repos[repotype]) + 1)
        self.dy_repos[repotype].append(repoid)
     
        # make our new repo obj
        newrepo = yum.yumRepo.YumRepository(repoid)
        newrepo.name = repoid
        newrepo.baseurl = [baseurl]
        newrepo.basecachedir = self.dy_basecachedir
        newrepo.metadata_expire = 0
        # add our new repo
        self.repos.add(newrepo)        
        # enable that repo
        self.repos.enableRepo(repoid)
        # setup the repo dirs/etc
        self.doRepoSetup(thisrepo=repoid)
        archlist = ['src']    
        self._getSacks(archlist=archlist, thisrepo=repoid)

    def dy_diff(self):
        add = []
        remove = []        
        modified = []
        newsack = yum.packageSack.ListPackageSack()
        for repoid in self.dy_repos['new']:
            newsack.addList(self.pkgSack.returnPackages(repoid=repoid))

        oldsack = yum.packageSack.ListPackageSack()
        for repoid in self.dy_repos['old']:
            oldsack.addList(self.pkgSack.returnPackages(repoid=repoid))

        for pkg in newsack.returnNewestByName():
            tot = self.pkgSack.searchNevra(name=pkg.name)
            if len(tot) == 1: # it's only in new
                add.append(pkg)
            if len(tot) > 1:
                if oldsack.contains(name=pkg.name):
                    newest_old = oldsack.returnNewestByName(name=pkg.name)[0]
                    modified.append((pkg, newest_old))
                else:
                    add.append(pkg)

        for pkg in oldsack.returnNewestByName():
            if len(newsack.searchNevra(name=pkg.name)) == 0:
                remove.append(pkg)
        
        return add, remove, modified


def parseArgs(args):
    """
       Parse the command line args. return a list of 'new' and 'old' repos
    """
    usage = """
    repodiff: take 2 or more repositories and return a list of added, removed and changed
              packages.
              
    repodiff --old=old_repo_baseurl --new=new_repo_baseurl """
    
    parser = OptionParser(version = "repodiff 0.2", usage=usage)
    # query options
    parser.add_option("-n", "--new", default=[], action="append",
                      help="new baseurl[s] for repos")
    parser.add_option("-o", "--old", default=[], action="append",
                      help="old baseurl[s] for repos")
    parser.add_option("-q", "--quiet", default=False, action='store_true')
    
    (opts, argsleft) = parser.parse_args()

    if not opts.new or not opts.old:
        parser.print_usage()
        sys.exit(1)
    
    return opts

def main(args):
    opts = parseArgs(args)

            
    my = DiffYum()
    my.dy_shutdown_all_other_repos()

    if not opts.quiet: print 'setting up repos'
    for r in opts.old:
        if not opts.quiet: print "setting up old repo %s" % r
        try:
            my.dy_setup_repo('old', r)
        except yum.Errors.RepoError, e:
            print "Could not setup repo at url  %s: %s" % (r, e)
            sys.exit(1)
    
    for r in opts.new:
        if not opts.quiet: print "setting up new repo %s" % r
        try:
            my.dy_setup_repo('new', r)
        except yum.Errors.RepoError, e:
            print "Could not setup repo at url %s: %s" % (r, e)
            sys.exit(1)
    if not opts.quiet: print 'performing the diff'
    add, rem, mod = my.dy_diff()
  

               
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
            msg = "%s-%s-%s" % (pkg.name, pkg.ver, pkg.rel)
            dashes = "-" * len(msg) 
            msg += "\n%s\n" % dashes
            # get newest clog time from the oldpkg
            # for any newer clog in pkg
            # print it
            oldlogs = oldpkg.changelog
            oldlogs.sort()
            oldlogs.reverse()
            if len(oldlogs):
                oldtime = oldlogs[0][0]
                clogdelta = []
                for (t, author, content) in  pkg.changelog:
                      if t > oldtime:
                          msg += "* %s %s\n%s\n\n" % (time.ctime(int(t)), author, content)

            print msg


if __name__ == "__main__":
    # ARRRRRRGH
    if not sys.stdout.isatty():
        import codecs, locale
        sys.stdout = codecs.getwriter(locale.getpreferredencoding())(sys.stdout)
    main(sys.argv[1:])
    

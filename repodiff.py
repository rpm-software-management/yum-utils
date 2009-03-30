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
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
# (c) 2007 Red Hat. Written by skvidal@fedoraproject.org

import yum
import sys
import datetime
import os
import locale
from yum.i18n import to_unicode

from optparse import OptionParser

class DiffYum(yum.YumBase):
    def __init__(self):
        yum.YumBase.__init__(self)
        self.dy_repos = {'old':[], 'new':[]}
        self.dy_basecachedir = yum.misc.getCacheDir()
        self.dy_archlist = ['src']
        
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
        newrepo.timestamp_check = False
        # add our new repo
        self.repos.add(newrepo)        
        # enable that repo
        self.repos.enableRepo(repoid)
        # setup the repo dirs/etc
        self.doRepoSetup(thisrepo=repoid)
        self._getSacks(archlist=self.dy_archlist, thisrepo=repoid)

    def dy_diff(self):
        add = []
        remove = []        
        modified = []
        obsoleted = {} # obsoleted = by
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
                    if newest_old.EVR != pkg.EVR:
                        modified.append((pkg, newest_old))
                else:
                    add.append(pkg)

        for pkg in oldsack.returnNewestByName():
            if len(newsack.searchNevra(name=pkg.name)) == 0:
                remove.append(pkg)


        for po in remove:
            for newpo in add:
                foundit = 0
                for obs in newpo.obsoletes:
                    if po.inPrcoRange('provides', obs):
                        foundit = 1
                        obsoleted[po] = newpo
                        break
                if foundit:
                    break
        
        ygh = yum.misc.GenericHolder()
        ygh.add = add
        ygh.remove = remove
        ygh.modified = modified
        ygh.obsoleted = obsoleted
                 
        return ygh


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
    parser.add_option("-a", "--archlist", default=[], action="append",
                      help="In addition to src.rpms, any arch you want to include")
    parser.add_option("-s", "--size", default=False, action='store_true',
                      help="Output size changes for any new->old packages")
    (opts, argsleft) = parser.parse_args()

    if not opts.new or not opts.old:
        parser.print_usage()
        sys.exit(1)

    # sort out the comma-separated crap we somehow inherited.    
    archlist = ['src']
    for a in opts.archlist:
        for arch in a.split(','):
            archlist.append(arch)

    opts.archlist = archlist             
    
    return opts

def main(args):
    opts = parseArgs(args)

            
    my = DiffYum()
    if opts.quiet:
        my.conf.debuglevel=0
        my.doLoggingSetup(my.conf.debuglevel, my.conf.errorlevel)
    
    my.dy_shutdown_all_other_repos()
    my.dy_archlist = opts.archlist
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
    ygh = my.dy_diff()
    

    total_sizechange = 0
    add_sizechange = 0
    remove_sizechange = 0
    if ygh.add:
        for pkg in sorted(ygh.add):
            print 'New package %s' % pkg.name
            print '        %s' % pkg.summary
            add_sizechange += int(pkg.size)
                
    if ygh.remove:
        for pkg in sorted(ygh.remove):
            print 'Removed package %s' % pkg.name
            if ygh.obsoleted.has_key(pkg):
                print 'Obsoleted by %s' % ygh.obsoleted[pkg]
            remove_sizechange += (int(pkg.size))
                
    if ygh.modified:
        print 'Updated Packages:\n'
        for (pkg, oldpkg) in sorted(ygh.modified):
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
                        msg += "* %s %s\n%s\n\n" % (datetime.date.fromtimestamp(int(t)).strftime("%a %b %d %Y"),
                               to_unicode(author), to_unicode(content))
            if opts.size:
                sizechange = int(pkg.size) - int(oldpkg.size)
                total_sizechange += sizechange
                msg += "\nSize Change: %s bytes\n" % sizechange

            print msg

    print 'Summary:'
    print 'Added Packages: %s' % len(ygh.add)
    print 'Removed Packages: %s' % len(ygh.remove)
    print 'Modified Packages: %s' % len(ygh.modified)
    if opts.size:
        print 'Size of added packages: %s' % add_sizechange
        print 'Size change of modified packages: %s' % total_sizechange
        print 'Size of removed packages: %s' % remove_sizechange
    
      
if __name__ == "__main__":
    # This test needs to be before locale.getpreferredencoding() as that
    # does setlocale(LC_CTYPE, "")
    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error, e:
        # default to C locale if we get a failure.
        print >> sys.stderr, 'Failed to set locale, defaulting to C'
        os.environ['LC_ALL'] = 'C'
        locale.setlocale(locale.LC_ALL, 'C')
        
    if True: # not sys.stdout.isatty():
        import codecs
        sys.stdout = codecs.getwriter(locale.getpreferredencoding())(sys.stdout)
        sys.stdout.errors = 'replace'

    main(sys.argv[1:])
    

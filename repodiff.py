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
# (c) 2007 Red Hat. Written by skvidal@fedoraproject.org

import yum
import sys
import datetime
import os
import locale
import rpmUtils.arch
from yum.i18n import to_unicode

from urlgrabber.progress import format_number

from optparse import OptionParser

def bkMG(num):
    ''' Call format_number() but deals with negative numbers. '''
    if num >= 0:
        return format_number(num)
    return '-' + format_number(-num)

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
        if baseurl.startswith("mirror:"):
            newrepo.mirrorlist = baseurl[len("mirror:"):]
        elif baseurl.startswith("/"):
            newrepo.baseurl = ["file:" + baseurl]
        else:
            newrepo.baseurl = [baseurl]
        newrepo.basecachedir = self.dy_basecachedir
        newrepo.base_persistdir = self.dy_basecachedir
        newrepo.metadata_expire = 0
        newrepo.timestamp_check = False
        # add our new repo
        self.repos.add(newrepo)        
        # enable that repo
        self.repos.enableRepo(repoid)
        # setup the repo dirs/etc
        self.doRepoSetup(thisrepo=repoid)
        if '*' in self.dy_archlist:
            # Include all known arches
            arches = rpmUtils.arch.arches
            archlist = list(set(arches.keys()).union(set(arches.values())))
        else:
            archlist = self.dy_archlist
        self._getSacks(archlist=archlist, thisrepo=repoid)

    def dy_diff(self, compare_arch=False):
        add = []
        remove = []        
        modified = []
        obsoleted = {} # obsoleted = by

        #  Originally we did this by setting up old and new repos. ... but as
        # a faster way, we can just go through all the pkgs once getting the
        # newest pkg with a repoid prefix of "old", dito. "new", and then
        # compare those directly.
        def _next_old_new(pkgs):
            """ Returns latest pair of (oldpkg, newpkg) for each package
                name. If that name doesn't exist, then it returns None for
                that package. """
            last = None
            npkg = opkg = None
            for pkg in sorted(pkgs):
                if compare_arch:
                    key = (pkg.name, pkg.arch)
                else:
                    key = pkg.name

                if last is None:
                    last = key
                if last != key:
                    yield opkg, npkg
                    opkg = npkg = None
                    last = key

                if pkg.repo.id.startswith('old'):
                    opkg = pkg
                else:
                    assert pkg.repo.id.startswith('new')
                    npkg = pkg
            if opkg is not None or npkg is not None: 
                yield opkg, npkg

        for opkg, npkg in _next_old_new(self.pkgSack.returnPackages()):
            if opkg is None:
                add.append(npkg)
            elif npkg is None:
                remove.append(opkg)
            elif not npkg.verEQ(opkg):
                modified.append((npkg, opkg))

        ao = {}
        for pkg in add:
            for obs_name in set(pkg.obsoletes_names):
                if obs_name not in ao:
                    ao[obs_name] = []
                ao[obs_name].append(pkg)

        #  Note that this _only_ shows something when you have an additional
        # package obsoleting a removed package. If the obsoleted package is
        # still there (somewhat "common") or the obsoleter is an update (dito)
        # you _don't_ get hits here.
        for po in remove:
            # Remember: Obsoletes are for package names only.
            poprovtup = (po.name, 'EQ', (po.epoch, po.ver, po.release))
            for newpo in ao.get(po.name, []):
                if newpo.inPrcoRange('obsoletes', poprovtup):
                    obsoleted[po] = newpo
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
    parser.add_option("--compare-arch", default=False, action='store_true',
                      help="When comparing binary repos. also compare the arch of packages, to see if they are different")
    parser.add_option("-s", "--size", default=False, action='store_true',
                      help="Output size changes for any new->old packages")
    parser.add_option("--downgrade", default=False, action='store_true',
                      help="Output upgrade/downgrade separately")
    parser.add_option("--simple",  default=False, action='store_true',
                      help="output simple format")
    (opts, argsleft) = parser.parse_args()

    if not opts.new or not opts.old:
        parser.print_usage()
        sys.exit(1)

    # sort out the comma-separated crap we somehow inherited.    
    archlist = []
    for a in opts.archlist:
        for arch in a.split(','):
            archlist.append(arch)
    if not archlist :
        archlist = ['src']

    opts.archlist = archlist             
    
    return opts

def _out_mod(opts, oldpkg, pkg, sizechange):
    if opts.simple:
        if opts.compare_arch:
            msg = "%s: %s ->  %s" % (pkg.name, oldpkg, pkg)
        else:
            msg = "%s: %s-%s-%s ->  %s-%s-%s" % (pkg.name, oldpkg.name, 
                                                 oldpkg.ver, oldpkg.rel,
                                                 pkg.name, pkg.ver,
                                                 pkg.rel)
    else:
        if opts.compare_arch:
            msg = "%s" % pkg
        else:
            msg = "%s-%s-%s" % (pkg.name, pkg.ver, pkg.rel)
        dashes = "-" * len(msg) 
        msg += "\n%s\n" % dashes
        # get newest clog time from the oldpkg
        # for any newer clog in pkg
        # print it
        oldlogs = oldpkg.changelog
        if len(oldlogs):
            #  Don't sort as that can screw the order up when time is the
            # same.
            oldtime    = oldlogs[0][0]
            oldauth    = oldlogs[0][1]
            oldcontent = oldlogs[0][2]
            for (t, author, content) in  pkg.changelog:
                if t < oldtime:
                    break
                if ((t == oldtime) and (author == oldauth) and
                    (content == oldcontent)):
                    break
                tm = datetime.date.fromtimestamp(int(t))
                tm = tm.strftime("%a %b %d %Y")
                msg += "* %s %s\n%s\n\n" % (tm, to_unicode(author),
                                            to_unicode(content))
            if opts.size:
                msg += "\nSize change: %s bytes\n" % sizechange

    print msg

def main(args):
    opts = parseArgs(args)

            
    my = DiffYum()
    archlist_changed = False
    if opts.archlist and not opts.archlist[0] == 'src':
        my.preconf.arch = opts.archlist[0]
        archlist_changed = True

    if opts.quiet:
        my.conf.debuglevel=0
        my.doLoggingSetup(my.conf.debuglevel, my.conf.errorlevel)
    
    my.conf.disable_excludes = ['all']
    my.dy_shutdown_all_other_repos()
    my.dy_archlist = opts.archlist
    if archlist_changed:
        my.dy_archlist += my.arch.archlist

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
    ygh = my.dy_diff(opts.compare_arch)
    


    total_sizechange = 0
    add_sizechange = 0
    remove_sizechange = 0
    mod_sizechange = 0
    up_sizechange = 0
    down_sizechange = 0
    upgraded_pkgs = 0
    downgraded_pkgs = 0
    if ygh.add:
        for pkg in sorted(ygh.add):
            if opts.compare_arch:
                print 'New package: %s' % pkg
            else:
                print 'New package: %s-%s-%s' % (pkg.name, pkg.ver, pkg.rel)
            print '             %s\n' % to_unicode(pkg.summary)
            add_sizechange += int(pkg.size)
                
    if ygh.remove:
        for pkg in sorted(ygh.remove):
            if opts.compare_arch:
                print 'Removed package: %s' % pkg
            else:
                print 'Removed package:  %s-%s-%s' % (pkg.name, pkg.ver,pkg.rel)
            if pkg in ygh.obsoleted:
                print 'Obsoleted by   :  %s' % ygh.obsoleted[pkg]
            remove_sizechange += (int(pkg.size))
                
    if ygh.modified:
        print '\nUpdated Packages:\n'
        for (pkg, oldpkg) in sorted(ygh.modified):
            if opts.downgrade and pkg.verLT(oldpkg):
                continue

            upgraded_pkgs += 1
            sizechange = None
            if opts.size:
                sizechange = int(pkg.size) - int(oldpkg.size)
                if opts.downgrade:
                    up_sizechange += sizechange
                else:
                    mod_sizechange += sizechange
            _out_mod(opts, oldpkg, pkg, sizechange)

        if opts.downgrade:
            print '\nDowngraded Packages:\n'
            for (pkg, oldpkg) in sorted(ygh.modified):
                if pkg.verGT(oldpkg):
                    continue

                downgraded_pkgs += 1
                sizechange = None
                if opts.size:
                    sizechange = int(pkg.size) - int(oldpkg.size)
                    down_sizechange += sizechange
                _out_mod(opts, oldpkg, pkg, sizechange)


    if (not ygh.add and not ygh.remove and not ygh.modified and
        not my.pkgSack.searchNevra(arch='src')):
        print "** No 'src' pkgs in any repo. maybe see docs. on --archlist?"

    print '\nSummary:'
    print 'Added Packages: %s' % len(ygh.add)
    print 'Removed Packages: %s' % len(ygh.remove)
    if not opts.downgrade:
        print 'Modified Packages: %s' % len(ygh.modified)
    else:
        print 'Upgraded Packages: %s' % upgraded_pkgs
        print 'Downgraded Packages: %s' % downgraded_pkgs
    if opts.size:
        print 'Size of added packages: %s (%s)' % (add_sizechange,
                                                   bkMG(add_sizechange))

        if not opts.downgrade:
            msg = 'Size change of modified packages: %s (%s)'
            print msg % (mod_sizechange, bkMG(mod_sizechange))

            total_sizechange = add_sizechange +mod_sizechange -remove_sizechange
        else:
            msg = 'Size change of upgraded packages: %s (%s)'
            print msg % (up_sizechange, bkMG(up_sizechange))
            msg = 'Size change of downgraded packages: %s (%s)'
            print msg % (down_sizechange, bkMG(down_sizechange))

            total_sizechange = (add_sizechange +
                                up_sizechange + down_sizechange -
                                remove_sizechange)

        msg = 'Size of removed packages: %s (%s)'
        print msg % (remove_sizechange, bkMG(remove_sizechange))
        msg = 'Size change: %s (%s)'
        print msg % (total_sizechange, bkMG(total_sizechange))
    
      
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
    

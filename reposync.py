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
# copyright 2006 Duke University
# author seth vidal

# sync all or the newest packages from a repo to the local path
# TODO:
#     have it copy over the metadata + groups files into the path, too
#     have it print out list of changes
#     make it work with mirrorlists (silly, really)
#     man page
#     more useful docs

import os
import sys
from optparse import OptionParser
from urlparse import urljoin

import yum
import yum.Errors
from yum.misc import getCacheDir
from yum.constants import *
from yum.packages import parsePackages
from repomd.packageSack import ListPackageSack

# for yum 2.4.X compat
def sortPkgObj(pkg1 ,pkg2):
    """sorts a list of yum package objects by name"""
    if pkg1.name > pkg2.name:
        return 1
    elif pkg1.name == pkg2.name:
        return 0
    else:
        return -1
        
class RepoSync(yum.YumBase):
    def __init__(self, opts):
        yum.YumBase.__init__(self)
        self.opts = opts
        
    def log(self, num, msg):
        if num < 3 and not self.opts.quiet:
            print msg
    


def parseArgs():
    usage = "usage: %s [options] package1 [package2] [package..]" % sys.argv[0]
    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--config", default='/etc/yum.conf',
        help='config file to use (defaults to /etc/yum.conf)')
#    parser.add_option("-a", "--arch", default=None,
#        help='check as if running the specified arch (default: current arch)')
    parser.add_option("-r", "--repoid", default=[], action='append',
        help="specify repo ids to query, can be specified multiple times (default is all enabled)")
    parser.add_option("-t", "--tempcache", default=False, action="store_true", 
        help="Use a temp dir for storing/accessing yum-cache")
    parser.add_option("-p", "--download_path", dest='destdir', 
        default=os.getcwd(), help="Path to download packages to")
    parser.add_option("-u", "--urls", default=False, action="store_true", 
        help="Just list urls of what would be downloaded, don't download")
    parser.add_option("-n", "--newest", default=True, action="store_false", 
        help="Toggle downloading only the newest packages(defaults to newest-only)")
    parser.add_option("-q", "--quiet", default=False, action="store_true", 
        help="Output as little as possible")
        
    (opts, args) = parser.parse_args()
    return (opts, args)


def main():
# TODO/FIXME
# gpg/sha checksum them
# make -a do something

    (opts, junk) = parseArgs()
    
    if not os.path.exists(opts.destdir) and not opts.urls:
        try:
            os.makedirs(opts.destdir)
        except OSError, e:
            print >> sys.stderr, "Error: Cannot create destination dir %s" % opts.destdir
            sys.exit(1)
    
    if not os.access(opts.destdir, os.W_OK) and not opts.urls:
        print >> sys.stderr, "Error: Cannot write to  destination dir %s" % opts.destdir
        sys.exit(1)
        
    my = RepoSync(opts=opts)
    my.doConfigSetup(fn=opts.config)
    
    # do the happy tmpdir thing if we're not root
    if os.geteuid() != 0 or opts.tempcache:
        cachedir = getCacheDir()
        if cachedir is None:
            print >> sys.stderr, "Error: Could not make cachedir, exiting"
            sys.exit(50)
            
        my.repos.setCacheDir(cachedir)

    if len(opts.repoid) > 0:
        myrepos = []
        
        # find the ones we want
        for glob in opts.repoid:
            myrepos.extend(my.repos.findRepos(glob))
        
        # disable them all
        for repo in my.repos.repos.values():
            repo.disable()
        
        # enable the ones we like
        for repo in myrepos:
            repo.enable()

    my.doRepoSetup()    
    my.doSackSetup()
    
    download_list = []
    
    if opts.newest:
        download_list = my.pkgSack.returnNewestByNameArch()
    else:
        download_list = list(my.pkgSack)
        
    download_list.sort(sortPkgObj)
    for pkg in download_list:
        repo = my.repos.getRepo(pkg.repoid)
        remote = pkg.returnSimple('relativepath')
        local = os.path.basename(remote)
        local = os.path.join(opts.destdir, local)
        if (os.path.exists(local) and 
            str(os.path.getsize(local)) == pkg.returnSimple('packagesize')):
            
            if not opts.quiet:
                my.errorlog(0,"%s already exists and appears to be complete" % local)
            continue

        if opts.urls:
            url = urljoin(repo.urls[0],remote)
            print '%s' % url
            continue

        # Disable cache otherwise things won't download
        repo.cache = 0
        my.log(2, 'Downloading %s' % os.path.basename(remote))
        repo.get(relative=remote, local=local)


if __name__ == "__main__":
    main()
    

#!/usr/bin/python

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

import yum
import yum.Errors
import sys
import os
import output
from urlgrabber.progress import TextMeter
from yum.logger import Logger
from yum.packages import parsePackages, returnBestPackages
from optparse import OptionParser
from urlparse import urljoin

def initYum():
    my = yum.YumBase()
    my.doConfigSetup()
    my.conf.setConfigOption('uid', os.geteuid())
    if my.conf.getConfigOption('uid') != 0:
        my.conf.setConfigOption('cache', 1)
    my.repos.setProgressBar(TextMeter(fo=sys.stdout))
    my.log = Logger(threshold=my.conf.getConfigOption('debuglevel'), 
    file_object =sys.stdout)
    my.repos.callback = output.CacheProgressCallback(my.log,
    my.errorlog, my.filelog)
    my.doRepoSetup()
    my.doSackSetup()
    return my

def parseArgs():
    usage = "usage: %s [options] package1 [package2] [package..]" % sys.argv[0]
    parser = OptionParser(usage=usage)
    parser.add_option("--destdir", default=".", dest="destdir",
      help='destination directory (defaults to current directory)')
    parser.add_option("--urls", default=False, dest="urls", action="store_true",
      help='just list the urls it would download instead of downloading')
    parser.add_option("--resolve", default=False, dest="resolve", action="store_true",
      help='resolve dependencies and download required packages')
    (opts, args) = parser.parse_args()
    if len(args) < 1: 
        parser.print_help()
        sys.exit(0)
    return (opts, args)

def main():
    (opts, args) = parseArgs()
    my = initYum()
    avail = my.pkgSack.returnPackages()
    toDownload = {}

    packages = args
    for pkg in packages:
        exactmatch, matched, unmatched = parsePackages(avail, [pkg])
        installable = yum.misc.unique(exactmatch + matched)
        if len(unmatched) > 0: # if we get back anything in unmatched, it fails
            my.errorlog(0, 'No Match for argument %s' % pkg)
            continue
        for newpkg in installable:
            toDownload.setdefault(newpkg.name,[]).append(newpkg.pkgtup)

    toDownload = returnBestPackages(toDownload)
    # If the user supplies to --resolve flag, resolve dependencies for
    # all packages
    # note this might require root access because the headers need to be
    # downloaded into the cachedir (is there a way around this)
    if opts.resolve:
        my.doTsSetup()
        my.localPackages = []
        # Act as if we were to install the packages in toDownload
        for x in toDownload:
            po = my.getPackageObject(x)
            my.tsInfo.addInstall(po)
            my.localPackages.append(po)
        # Resolve dependencies
        my.resolveDeps()
        # Add newly added packages to the toDownload list
        for x in my.tsInfo.getMembers():
            pkgtup = x.pkgtup
            if not pkgtup in toDownload:
                toDownload.append(pkgtup)
        
    for pkg in toDownload:
        n,a,e,v,r = pkg
        packages =  my.pkgSack.searchNevra(n,e,v,r,a)
        for download in packages:
            repo = my.repos.getRepo(download.repoid)
            remote = download.returnSimple('relativepath')
            if opts.urls:
                url = urljoin(repo.urls[0],remote)
                my.log(0, '%s' % url)
                continue
            local = os.path.basename(remote)
            local = os.path.join(opts.destdir, local)
            if (os.path.exists(local) and 
                str(os.path.getsize(local)) == download.returnSimple('packagesize')):
                my.errorlog(0,"%s already exists and appears to be complete" % local)
                continue
            # Disable cache otherwise things won't download
            repo.cache = 0
            repo.get(relative=remote, local=local)

if __name__ == '__main__':
    main()

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

import sys

sys.path.insert(0, '/usr/share/yum-cli')

import yum
import yum.Errors
import os
import shutil
import output
import rpmUtils.arch
from urlgrabber.progress import TextMeter
import logging
from yum.packages import parsePackages
from yum.misc import getCacheDir
from optparse import OptionParser
from urlparse import urljoin

def initYum(yumconfigfile):
    global logger
    my = yum.YumBase()
    my.doConfigSetup(fn=yumconfigfile,init_plugins=False) # init yum, without plugins
    my.conf.uid = os.geteuid()
    if my.conf.uid != 0:
        cachedir = getCacheDir()
        if cachedir is None:
            logger.error("Error: Could not make cachedir, exiting")
            sys.exit(50)
        my.repos.setCacheDir(cachedir)
    my.repos.setProgressBar(TextMeter(fo=sys.stdout))
    my.repos.callback = output.CacheProgressCallback()

    return my

def parseArgs():
    usage = "usage: %s [options] package1 [package2] [package..]" % sys.argv[0]
    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--config", default='/etc/yum.conf',
      help='config file to use (defaults to /etc/yum.conf)')
    parser.add_option("--destdir", default=".", dest="destdir",
      help='destination directory (defaults to current directory)')
    parser.add_option("--urls", default=False, dest="urls", action="store_true",
      help='just list the urls it would download instead of downloading')
    parser.add_option("--resolve", default=False, dest="resolve", action="store_true",
      help='resolve dependencies and download required packages')
    parser.add_option("--source", default=False, dest="source", action="store_true",
      help='operate on source packages')
    parser.add_option("-e","--enablerepo", default=[], action="append", dest="repo",
      help='enable repository')

    (opts, args) = parser.parse_args()
    if len(args) < 1: 
        parser.print_help()
        sys.exit(0)
    return (opts, args)

def main():
    global logger
    logger = logging.getLogger("yum.verbose.yumdownloader")
    (opts, args) = parseArgs()
    my = initYum(opts.config)

    if len(opts.repo) > 0:
        myrepos = []
        
        # find the ones we want
        for glob in opts.repo:
            myrepos.extend(my.repos.findRepos(glob))
        
        # disable them all
        for repo in my.repos.repos.values():
            repo.disable()
        
        # enable the ones we like
        for repo in myrepos:
            repo.enable()

    my.doRpmDBSetup()
    my.doRepoSetup()
    archlist = None
    if opts.source:
        archlist = rpmUtils.arch.getArchList() + ['src']

    my.doSackSetup(archlist=archlist)

    avail = my.pkgSack.returnPackages()

    toDownload = []

    packages = args
    for pkg in packages:
        toActOn = []
        exactmatch, matched, unmatched = parsePackages(avail, [pkg])
        installable = yum.misc.unique(exactmatch + matched)
        if len(unmatched) > 0: # if we get back anything in unmatched, it fails
            logger.error('No Match for argument %s' % pkg)
            continue

        for newpkg in installable:
            # This is to fix Bug 469
            # If there are matches to the package argument given but there
            # are no source packages, this can be caused because the
            # source rpm this is built from has a different name
            # for example: nscd is built from the glibc source rpm
            # We find this name by parsing the sourcerpm filename
            # (this is ugly but it appears to work)
            # And finding a package with arch src and the same
            # ver and rel as the binary package
            # That should be the source package
            # Note we do not use the epoch to search as the epoch for the
            # source rpm might be different from the binary rpm (see
            # for example mod_ssl)
            if opts.source and newpkg.arch != 'src':
                name = newpkg.returnSimple('sourcerpm').rsplit('-',2)[0]
                src = my.pkgSack.searchNevra(name=name, arch = 'src',
                  ver = newpkg.version,
                  rel = newpkg.release
                )
                toActOn.extend(src)
            else:
                toActOn.append(newpkg)

        if toActOn:
            if opts.source:
                toDownload.extend(my.bestPackagesFromList(toActOn, 'src'))
            else:
                toDownload.extend(my.bestPackagesFromList(toActOn))
    
    # If the user supplies to --resolve flag, resolve dependencies for
    # all packages
    # note this might require root access because the headers need to be
    # downloaded into the cachedir (is there a way around this)
    if opts.resolve:
        my.doTsSetup()
        my.localPackages = []
        # Act as if we were to install the packages in toDownload
        for po in toDownload:
            my.tsInfo.addInstall(po)
            my.localPackages.append(po)
        # Resolve dependencies
        my.resolveDeps()
        # Add newly added packages to the toDownload list
        for pkg in my.tsInfo.getMembers():
            if not pkg in toDownload:
                toDownload.append(pkg)
        
    for pkg in toDownload:
        n,a,e,v,r = pkg.pkgtup
        packages =  my.pkgSack.searchNevra(n,e,v,r,a)
        for download in packages:
            repo = my.repos.getRepo(download.repoid)
            remote = download.returnSimple('relativepath')
            if opts.urls:
                url = urljoin(repo.urls[0],remote)
                logger.info('%s' % url)
                continue
            local = os.path.basename(remote)
            local = os.path.join(opts.destdir, local)
            if (os.path.exists(local) and 
                str(os.path.getsize(local)) == download.returnSimple('packagesize')):
                logger.error("%s already exists and appears to be complete" % local)
                continue
            # Disable cache otherwise things won't download
            repo.cache = 0
            download.localpath = local # Hack: to set the localpath we want.
            path = repo.getPackage(download)

            if not os.path.exists(local) or not os.path.samefile(path, local):
                progress = TextMeter()
                progress.start(basename=os.path.basename(local),
                               size=os.stat(path).st_size)
                shutil.copy2(path, local)
                progress.end(progress.size)

if __name__ == '__main__':
    main()

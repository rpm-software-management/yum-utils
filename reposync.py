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
# copyright 2006 Duke University
# author seth vidal

# sync all or the newest packages from a repo to the local path
# TODO:
#     have it print out list of changes
#     make it work with mirrorlists (silly, really)
#     man page/more useful docs
#     deal nicely with a package changing but not changing names (ie: replacement)

# criteria
# if a package is not the same and smaller then reget it
# if a package is not the same and larger, delete it and get it again
# always replace metadata files if they're not the same.





import os
import sys
import shutil
import stat

from optparse import OptionParser
from urlparse import urljoin

from yumutils.i18n import _

import yum
import yum.Errors
from yum.packageSack import ListPackageSack
import rpmUtils.arch
import logging
from urlgrabber.progress import TextMeter, TextMultiFileMeter
import urlgrabber

class RepoSync(yum.YumBase):
    def __init__(self, opts):
        yum.YumBase.__init__(self)
        self.logger = logging.getLogger('yum.verbose.reposync')
        self.opts = opts

def localpkgs(directory):
    names = os.listdir(directory)

    cache = {}
    for name in names:
        fn = os.path.join(directory, name)
        try:
            st = os.lstat(fn)
        except os.error:
            continue
        if stat.S_ISDIR(st.st_mode):
            subcache = localpkgs(fn)
            for pkg in subcache.keys():
                cache[pkg] = subcache[pkg]
        elif stat.S_ISREG(st.st_mode) and name.endswith(".rpm"):
            cache[name] = {'path': fn, 'size': st.st_size, 'device': st.st_dev}
    return cache

def parseArgs():
    usage = _("""
    Reposync is used to synchronize a remote yum repository to a local 
    directory using yum to retrieve the packages.
    
    %s [options]
    """) % sys.argv[0]

    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--config", default='/etc/yum.conf',
        help=_('config file to use (defaults to /etc/yum.conf)'))
    parser.add_option("-a", "--arch", default=None,
        help=_('act as if running the specified arch (default: current arch, note: does not override $releasever. x86_64 is a superset for i*86.)'))
    parser.add_option("--source", default=False, dest="source", action="store_true",
                      help=_('operate on source packages'))
    parser.add_option("-r", "--repoid", default=[], action='append',
        help=_("specify repo ids to query, can be specified multiple times (default is all enabled)"))
    parser.add_option("-e", "--cachedir",
        help=_("directory in which to store metadata"))
    parser.add_option("-t", "--tempcache", default=False, action="store_true",
        help=_("Use a temp dir for storing/accessing yum-cache"))
    parser.add_option("-d", "--delete", default=False, action="store_true",
        help=_("delete local packages no longer present in repository"))
    parser.add_option("-p", "--download_path", dest='destdir',
        default=os.getcwd(), help=_("Path to download packages to: defaults to current dir"))
    parser.add_option("--norepopath", dest='norepopath', default=False, action="store_true",
        help=_("Don't add the reponame to the download path. Can only be used when syncing a single repository (default is to add the reponame)"))
    parser.add_option("-g", "--gpgcheck", default=False, action="store_true",
        help=_("Remove packages that fail GPG signature checking after downloading"))
    parser.add_option("-u", "--urls", default=False, action="store_true",
        help=_("Just list urls of what would be downloaded, don't download"))
    parser.add_option("-n", "--newest-only", dest='newest', default=False, action="store_true",
        help=_("Download only newest packages per-repo"))
    parser.add_option("-q", "--quiet", default=False, action="store_true",
        help=_("Output as little as possible"))
    parser.add_option("-l", "--plugins", default=False, action="store_true",
        help=_("enable yum plugin support"))
    parser.add_option("-m", "--downloadcomps", default=False, action="store_true",
        help=_("also download comps.xml"))
    parser.add_option("", "--download-metadata", dest="downloadmd",
        default=False, action="store_true",
        help=_("download all the non-default metadata"))
    (opts, args) = parser.parse_args()
    return (opts, args)


def main():
    (opts, dummy) = parseArgs()

    if not os.path.exists(opts.destdir) and not opts.urls:
        try:
            os.makedirs(opts.destdir)
        except OSError, e:
            print >> sys.stderr, _("Error: Cannot create destination dir %s") % opts.destdir
            sys.exit(1)

    if not os.access(opts.destdir, os.W_OK) and not opts.urls:
        print >> sys.stderr, _("Error: Cannot write to  destination dir %s") % opts.destdir
        sys.exit(1)

    my = RepoSync(opts=opts)
    my.doConfigSetup(fn=opts.config, init_plugins=opts.plugins)

    # Force unprivileged users to have a private temporary cachedir
    # if they've not given an explicit cachedir
    if os.getuid() != 0 and not opts.cachedir:
        opts.tempcache = True

    if opts.tempcache:
        if not my.setCacheDir(force=True, reuse=False):
            print >> sys.stderr, _("Error: Could not make cachedir, exiting")
            sys.exit(50)
        my.conf.uid = 1 # force locking of user cache
    elif opts.cachedir:
        my.repos.setCacheDir(opts.cachedir)

    # Lock if they've not given an explicit cachedir
    if not opts.cachedir:
        try:
            my.doLock()
        except yum.Errors.LockError, e:
            print >> sys.stderr, _("Error: %s") % e
            sys.exit(50)

    #  Use progress bar display when downloading repo metadata
    # and package files ... needs to be setup before .repos (ie. RHN/etc.).
    if not opts.quiet:
        my.repos.setProgressBar(TextMeter(fo=sys.stdout), TextMultiFileMeter(fo=sys.stdout))
    my.doRepoSetup()

    if len(opts.repoid) > 0:
        myrepos = []

        # find the ones we want
        for glob in opts.repoid:
            add_repos = my.repos.findRepos(glob)
            if not add_repos:
                print >> sys.stderr, _("Warning: cannot find repository %s") % glob
                continue
            myrepos.extend(add_repos)

        if not myrepos:
            print >> sys.stderr, _("No repositories found")
            sys.exit(1)

        # disable them all
        for repo in my.repos.repos.values():
            repo.disable()

        # enable the ones we like
        for repo in myrepos:
            repo.enable()

    # --norepopath can only be sensibly used with a single repository:
    if len(my.repos.listEnabled()) > 1 and opts.norepopath:
        print >> sys.stderr, _("Error: Can't use --norepopath with multiple repositories")
        sys.exit(1)

    try:
        arches = rpmUtils.arch.getArchList(opts.arch)
        if opts.source:
            arches += ['src']
        my.doSackSetup(arches)
    except yum.Errors.RepoError, e:
        print >> sys.stderr, _("Error setting up repositories: %s") % e
        # maybe this shouldn't be entirely fatal
        sys.exit(1)

    exit_code = 0
    for repo in my.repos.listEnabled():
        reposack = ListPackageSack(my.pkgSack.returnPackages(repoid=repo.id))

        if opts.newest:
            download_list = reposack.returnNewestByNameArch()
        else:
            download_list = list(reposack)

        if opts.norepopath:
            local_repo_path = opts.destdir
        else:
            local_repo_path = opts.destdir + '/' + repo.id

        if opts.delete and os.path.exists(local_repo_path):
            current_pkgs = localpkgs(local_repo_path)

            download_set = {}
            for pkg in download_list:
                remote = pkg.returnSimple('relativepath')
                rpmname = os.path.basename(remote)
                download_set[rpmname] = 1

            for pkg in current_pkgs:
                if pkg in download_set:
                    continue

                if not opts.quiet:
                    my.logger.info("Removing obsolete %s", pkg)
                os.unlink(current_pkgs[pkg]['path'])

        if opts.downloadcomps or opts.downloadmd:

            if not os.path.exists(local_repo_path):
                try:
                    os.makedirs(local_repo_path)
                except IOError, e:
                    my.logger.error("Could not make repo subdir: %s" % e)
                    my.closeRpmDB()
                    sys.exit(1)

            if opts.downloadcomps:
                wanted_types = ['group']

            if opts.downloadmd:
                wanted_types = repo.repoXML.fileTypes()

            for ftype in repo.repoXML.fileTypes():
                if ftype in ['primary', 'primary_db', 'filelists',
                             'filelists_db', 'other', 'other_db']:
                    continue
                if ftype not in wanted_types:
                    continue

                try:
                    resultfile = repo.retrieveMD(ftype)
                    basename = os.path.basename(resultfile)
                    if ftype == 'group' and opts.downloadcomps: # for compat with how --downloadcomps saved the comps file always as comps.xml
                        basename = 'comps.xml'
                    shutil.copyfile(resultfile, "%s/%s" % (local_repo_path, basename))
                except yum.Errors.RepoMDError, e:
                    if not opts.quiet:
                        my.logger.error("Unable to fetch metadata: %s" % e)

        remote_size = 0
        if not opts.urls:
            for pkg in download_list:
                remote = pkg.returnSimple('relativepath')
                local = local_repo_path + '/' + remote
                sz = int(pkg.returnSimple('packagesize'))
                if os.path.exists(local) and os.path.getsize(local) == sz:
                    continue
                remote_size += sz

        if hasattr(urlgrabber.progress, 'text_meter_total_size'):
            urlgrabber.progress.text_meter_total_size(remote_size)

        download_list.sort(key=lambda pkg: pkg.name)
        if opts.urls:
            for pkg in download_list:
                print urljoin(pkg.repo.urls[0], pkg.relativepath)
            continue

        # create dest dir
        if not os.path.exists(local_repo_path):
            os.makedirs(local_repo_path)

        # set localpaths
        for pkg in download_list:
            rpmfn = pkg.remote_path
            pkg.localpath = os.path.join(local_repo_path, rpmfn)
            pkg.repo.copy_local = True
            pkg.repo.cache = 0
            localdir = os.path.dirname(pkg.localpath)
            if not os.path.exists(localdir):
                os.makedirs(localdir)

        # use downloader from YumBase
        probs = my.downloadPkgs(download_list)
        if probs:
            exit_code = 1
            for key in probs:
                for error in probs[key]:
                    my.logger.error('%s: %s', key, error)

        if opts.gpgcheck:
            for pkg in download_list:
                result, error = my.sigCheckPkg(pkg)
                if result != 0:
                    rpmfn = os.path.basename(pkg.remote_path)
                    if result == 1:
                        my.logger.warning('Removing %s, due to missing GPG key.' % rpmfn)
                    elif result == 2:
                        my.logger.warning('Removing %s due to failed signature check.' % rpmfn)
                    else:
                        my.logger.warning('Removing %s due to failed signature check: %s' % rpmfn)
                    os.unlink(pkg.localpath)
                    exit_code = 1
                    continue

    my.closeRpmDB()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

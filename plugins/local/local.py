#! /usr/bin/python -tt
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
#
#
# Copyright Red Hat Inc. 2009
#
# Author: James Antill <james.antill@redhat.com>
#

# FIXME: Doesn't copy updateinfo over
# TODO: Add command to explicitly download pkgs and add them to the repo.
# TODO: Some way to say "don't copy from these repos." or "only copy from these"
#       so we can just get updates/rawhide and not fedora (which doesn't lose
#       packages).

import os
import shutil
import yum
from yum.plugins import TYPE_CORE

requires_api_version = '2.5'
plugin_type = (TYPE_CORE,)

def_local_repo_dir = '/var/lib/yum/plugins/local'
local_repo_dir = ''

def prereposetup_hook(conduit):
    global local_repo_dir
    local_repo_dir  = conduit.confString('main', 'repodir',
                                         default=def_local_repo_dir)
    try:
        d_mtime = os.stat(local_repo_dir).st_mtime
        r_mtime = os.stat("%s/repodata/repomd.xml" % local_repo_dir).st_mtime
        if d_mtime > r_mtime:
            _rebuild(conduit)
    except:
        pass

def postdownload_hook(conduit):
    if conduit.getErrors() or os.geteuid():
        return


    reg  = False
    done = 0
    for pkg in conduit.getDownloadPackages():
        fname = pkg.localPkg()
        if fname.startswith(local_repo_dir):
            reg = True
            continue

        dest = local_repo_dir + '/' + os.path.basename(fname)
        if os.path.exists(dest):
            continue

        if not done and not os.path.exists(local_repo_dir):
            os.makedirs(local_repo_dir)
        done += 1
        shutil.copy2(fname, dest)

    if reg:
        if hasattr(conduit, 'registerPackageName'):
            conduit.registerPackageName("yum-plugin-local")

    if not done:
        return
    _rebuild(conduit, done)
    _reposetup(conduit)

def _rebuild(conduit, done=None):
    enabled = conduit.confBool('createrepo', 'enabled', default=True)
    if not enabled:
        return

    cache_dir = conduit.confString('createrepo', 'cachedir', default=None)
    checksum  = conduit.confString('createrepo', 'checksum', default=None)

    quiet     = conduit.confBool('createrepo', 'quiet',     default=True)
    verbose   = conduit.confBool('createrepo', 'verbose',   default=False)
    skip_stat = conduit.confBool('createrepo', 'skip_stat', default=False)
    unique_md = conduit.confBool('createrepo', 'unique_md_filenames',
                                 default=False)
    update = conduit.confBool('createrepo', 'update', default=True)
    databases = conduit.confBool('createrepo', 'databases', default=True)

    deltas = conduit.confBool('createrepo', 'deltas', default=False)
    num_deltas = conduit.confInt('createrepo', 'num-deltas', default=None)
    old_package_dirs = conduit.confString('createrepo', 'oldpackagedirs', default=local_repo_dir)

    if conduit._base.verbose_logger.isEnabledFor(yum.logginglevels.DEBUG_3):
        quiet = False

    args = ["createrepo"]
    if quiet:
        args.append("--quiet")
    if verbose:
        args.append("--verbose")
    if databases:
        args.append("--database")
    if update:
        args.append("--update")
    if unique_md:
        args.append("--unique-md-filenames")
    if checksum is not None:
        args.append("--checksum")
        args.append(checksum)
    if skip_stat:
        args.append("--skip-stat")
    if cache_dir is not None:
        args.append("--cachedir")
        args.append(cache_dir)
    if deltas:
        args.append('--deltas')
        args.append('--oldpackagedirs')
        args.append(old_package_dirs)
    if num_deltas is not None:
        args.append('--num-deltas')
        args.append(num_deltas)
    args.append(local_repo_dir)
    if not quiet:
        if done is None:
            conduit.info(2, "== Rebuilding _local repo. ==")
        else:
            msg = "== Rebuilding _local repo. with %u new packages ==" % done
            conduit.info(2, msg)
    os.spawnvp(os.P_WAIT, "createrepo", args)
    # For the prerepo. check
    os.utime("%s/repodata/repomd.xml" % local_repo_dir, None)
    if not quiet:
        conduit.info(2, "== Done rebuild of _local repo. ==")

def _reposetup(conduit):
    lrepo = [repo for repo in conduit._base.repos.listEnabled()
             if repo.id == "_local"]
    if lrepo:
        lrepo = lrepo[0]
        os.unlink("%s/cachecookie" % lrepo.cachedir)
        return

    conf_fname = '/etc/yum.repos.d/_local.repo'
    if os.path.exists(conf_fname):
        return

    open(conf_fname, "wb").write("""\
[_local]
name=Automatic local repo. (manged by the "local" yum plugin).
baseurl=file:%s
enabled=1
gpgcheck=true
#  Metadata expire could be set to "never" because the local plugin will
# automatically cause a cache refresh when new packages are added. However
# it's really cheap to check, and this way people can dump stuff in whenever
# and it never gets out of sync. for long.
metadata_expire=1h
#  Make cost smaller, as we know it's "local". If you really want to be sure,
# you can do this ... but the name will do pretty much the same thing, and that
# way we can also see the other packages (with: --showduplicates list).
# cost=500
""" % local_repo_dir)

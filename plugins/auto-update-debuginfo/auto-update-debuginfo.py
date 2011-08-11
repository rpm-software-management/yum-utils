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
#
# by James Antill <james@fedoraproject.org>
#
# This plugin enables the debuginfo repos. if you have a debuginfo rpm
# installed.

from yum.plugins import TYPE_CORE

import os, os.path
import re
import fnmatch

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)

def _check_man_disable(mdrs, di):
    """ Was this repo. manually disabled. """
    for match in mdrs:
        if match(di):
            return True
    return False

def enable_debuginfo_repos(yb, conduit):
    mdrs = set()
    opts, args = conduit.getCmdLine()
    if hasattr(opts, 'repos'):
        for opt, repoexp in opts.repos:
            if opt == '--disablerepo':
                mdrs.add(repoexp)
    mdrs = [re.compile(fnmatch.translate(x)).match for x in mdrs]

    baserepos = {}
    for repo in yb.repos.listEnabled():
        baserepos[repo.id] = repo
    for repoid in baserepos:
        di = '%s-debuginfo' % repoid
        if di in baserepos:
            continue
        if _check_man_disable(mdrs, di):
            continue
        baserepo = baserepos[repoid]
        for r in yb.repos.findRepos(di):
            conduit.info(3, 'Enabling %s: %s' % (r.id, r.name))
            r.enable()
            r.skip_if_unavailable = True
            # Note: This is shared with debuginfo-install
            for opt in ['repo_gpgcheck', 'gpgcheck', 'cost']:
                if hasattr(r, opt):
                    setattr(r, opt, getattr(baserepo, opt))

def _read_cached(cfname):
    try:
        fo = open(cfname)
        crpmdbv = fo.readline()[:-1]
        cnum    = int(fo.readline())
        return crpmdbv, cnum
    except:
        return None, None

def _write_cached(cfname, rpmdbv, num):
    cdname = os.path.dirname(cfname)
    if not os.access(cdname, os.W_OK):
        if os.path.exists(cdname):
            return

        try:
            os.makedirs(cdname)
        except (IOError, OSError), e:
            return

    try:
        fo = open(cfname + ".tmp", "w")
    except (IOError, OSError), e:
        return

    fo.write(str(rpmdbv))
    fo.write('\n')
    fo.write(str(num))
    fo.write('\n')
    fo.close()
    os.rename(cfname + ".tmp", cfname)

def prereposetup_hook(conduit):
    yb = conduit._base

    caching = hasattr(yb.rpmdb, 'simpleVersion')
    num = None
    if caching:
        cfname = yb.conf.persistdir + '/plugins/auto-update-debuginfo/num'
        crpmdbv, num = _read_cached(cfname)
        if num is not None:
            rpmdbv = yb.rpmdb.simpleVersion(main_only=True)[0]
            if rpmdbv != crpmdbv:
                num = None

    if num is None:
        num = len(yb.rpmdb.returnPackages(patterns=['*-debuginfo']))
        if caching:
            rpmdbv = yb.rpmdb.simpleVersion(main_only=True)[0]
            _write_cached(cfname, rpmdbv, num)

    if num:
        if hasattr(conduit, 'registerPackageName'):
            conduit.registerPackageName("yum-plugin-auto-update-debug-info")
        conduit.info(3, "Found %d installed debuginfo package(s)" % num)
        enable_debuginfo_repos(yb, conduit)

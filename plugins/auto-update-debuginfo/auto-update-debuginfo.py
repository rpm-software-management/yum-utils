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

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)

def enable_debuginfo_repos(yb, conduit):
    repos = {}
    for repo in yb.repos.listEnabled():
        repos[repo.id] = repo
    for repoid in repos:
        di = '%s-debuginfo' % repoid
        if di in repos:
            continue
        repo = repos[repoid]
        for r in yb.repos.findRepos(di):
            conduit.info(2, 'Enabling %s: %s' % (r.id, r.name))
            r.enable()
            # Note: This is shared with debuginfo-install
            for opt in ['repo_gpgcheck', 'gpgcheck', 'cost',
                        'skip_if_unavailable']:
                if hasattr(r, opt):
                    setattr(r, opt, getattr(repo, opt))

def prereposetup_hook(conduit):
    yb = conduit._base
    num = len(yb.rpmdb.returnPackages(patterns=['*-debuginfo']))
    if num:
        if hasattr(conduit, 'registerPackageName'):
            conduit.registerPackageName("yum-plugin-auto-update-debug-info")
        conduit.info(2, "Found %d installed debuginfo package(s)" % num)
        enable_debuginfo_repos(yb, conduit)

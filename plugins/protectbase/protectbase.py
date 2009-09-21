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
# by Menno Smits <menno@freshfoo.com>

'''
This plugin allows certain repositories to be protected. Packages in the
protected repositories can't be overridden by packages in non-protected
repositories even if the non-protected repo has a later version.

This is mainly useful for preventing 3rd party repositories from interfering
with packages from core, updates, extras and livna.

Enable the plugin and add 'protect=yes' to the config of all repos you want to
protect.
'''

from yum.plugins import TYPE_CORE
from yum import config 

requires_api_version = '2.4'
plugin_type = (TYPE_CORE,)

def config_hook(conduit):
    '''Add options to Yum's configuration
    '''
    config.YumConf.protect = config.BoolOption(False)
    config.RepoConf.protect = config.Inherit(config.YumConf.protect)

def exclude_hook(conduit):
    '''Exclude packages from non-protected repositories that may upgrade
    packages from protected repositories.
    '''
    cnt = 0

    allrepos = conduit.getRepos().listEnabled()

    for repo1 in allrepos:
        if repo1.enabled and repo1.protect:
            repo1pkgs = _pkglisttodict(conduit.getPackages(repo1))

            for repo2 in allrepos:
                if not repo2.enabled or repo2.protect:
                    continue

                for po in conduit.getPackages(repo2):
                    if repo1pkgs.has_key(po.name):
                        conduit.delPackage(po)
                        cnt += 1

    if cnt:
        if hasattr(conduit, 'registerPackageName'):
            conduit.registerPackageName("yum-plugin-protectbase")
    conduit.info(2, '%d packages excluded due to repository protections' % cnt)

def _pkglisttodict(pl):
    out = {}
    for p in pl:
        out[p.name] = 1
    return out



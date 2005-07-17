'''
This plugin allows certain repositories to be protected. Packages in the
protected repositories can't be overridden by packages in non-protected
repositories even if the non-protected repo has a later version.

This is mainly useful for preventing 3rd party repositories from interfering
with packages from base, updates, extras and livna.

Enable the plugin and add 'protect=1' to the config of all repos you want to
protect.
'''

from yum.constants import *
from yum.plugins import TYPE_CORE

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)

def config_hook(conduit):
    conduit.registerOpt('protect', PLUG_OPT_BOOL, PLUG_OPT_WHERE_REPO, False)

def exclude_hook(conduit):
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

    conduit.info(2, '%d packages excluded due to repository protections' % cnt)

def _pkglisttodict(pl):
    out = {}
    for p in pl:
        out[p.name] = 1
    return out



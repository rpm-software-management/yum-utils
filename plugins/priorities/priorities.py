#!/usr/bin/env python
#
# yum-plugin-priorities 0.0.5
#
# Copyright (c) 2006 Daniel de Kok
#
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
# This plugins is inspired by the protectbase plugin, and enables/disables
# packages based on a repository priority.
#
# You can install this plugin by copying it to /usr/lib/yum-plugins. To
# enable this plugin, make sure that you have 'plugins=1' in /etc/yum.conf,
# and create the file /etc/yum/pluginconf.d/priorities.conf with the
# following content:
#
# [main]
# enabled=1
#
# If you also want the plugin to protect high-priority repositories against
# obsoletes in low-priority repositories, enable the 'check_obsoletes' bool:
#
# check_obsoletes=1
#
# You can add priorities to repositories, by adding the line:
#
# priority=N
#
# to the repository entry, where N is an integer number. The default
# priority for repositories is 99. The repositories with the lowest
# number have the highest priority.
#
# Please report errors to Daniel de Kok <danieldk@pobox.com>

from yum.constants import *
from yum.plugins import TYPE_CORE
from yum import config
import yum

check_obsoletes = False

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)

def config_hook(conduit):
    global check_obsoletes
    check_obsoletes = conduit.confBool('main', 'check_obsoletes', default=False)
    if yum.__version__ >= '2.5.0':
        # New style : yum >= 2.5
        config.RepoConf.priority = config.IntOption(99)
    else:
        # Old add extra options style
        conduit.registerOpt('priority', PLUG_OPT_INT, PLUG_OPT_WHERE_REPO, 99)

def exclude_hook(conduit):
    cnt = 0
    allrepos = conduit.getRepos().listEnabled()

    if check_obsoletes:
        obsoletes = conduit._base.pkgSack.returnObsoletes() 

    # Build a dictionary with package priorities. Since we handle obsoletes
    # archless, also build an archless package priority dictionary for
    # obsolete handling.
    pkg_priorities = dict()
    if check_obsoletes:
        pkg_priorities_archless = dict() 
    for repo in allrepos:
        if repo.enabled:
            repopkgs = _pkglist_to_dict(conduit.getPackages(repo), repo.priority)
            _mergeprioritydicts(pkg_priorities, repopkgs)

            if check_obsoletes:
                repopkgs_archless = _pkglist_to_archless_dict(conduit.getPackages(repo), repo.priority)
                _mergeprioritydicts(pkg_priorities_archless, repopkgs_archless)

    # Eliminate packages that have a low priority
    for repo in allrepos:
        if repo.enabled:
            for po in conduit.getPackages(repo):
                key = "%s.%s" % (po.name,po.arch)
                if pkg_priorities.has_key(key) and pkg_priorities[key] < repo.priority:
                    conduit.delPackage(po)
                    cnt += 1
                    conduit.info(3," --> %s from %s excluded (priority)" % (po,po.repoid))
                
                # If this packages obsoletes other packages, check whether
                # one of the obsoleted packages is not available through
                # a repo with a higher priority. If so, remove this package.
                if check_obsoletes:
                    if obsoletes.has_key(po.pkgtup):
                        obsolete_pkgs = obsoletes[po.pkgtup]
                        for obsolete_pkg in obsolete_pkgs:
                            pkg_name = obsolete_pkg[0]
                            if pkg_priorities_archless.has_key(pkg_name) and pkg_priorities_archless[pkg_name] < repo.priority:
                                conduit.delPackage(po)
                                cnt += 1
                                conduit.info(3," --> %s from %s excluded (priority)" % (po,po.repoid))
                                break
    conduit.info(2, '%d packages excluded due to repository priority protections' % cnt)

def _pkglist_to_dict(pl, priority):
    out = dict()
    for p in pl:
        key = "%s.%s" % (p.name,p.arch)
        out[key] = priority
    return out

def _pkglist_to_archless_dict(pl, priority):
    out = dict()
    for p in pl:
        out[p.name] = priority
    return out

def _mergeprioritydicts(dict1, dict2):
    for package in dict2.keys():
        if not dict1.has_key(package) or dict2[package] < dict1[package]:
            dict1[package] = dict2[package]

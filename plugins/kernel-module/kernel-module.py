# Plugin for handling upgrades of kernel module packages named in
# kernel-module-<module name>-<uname -r> style as seen for example on livna.org
#
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
# by Panu Matilainen <pmatilai@laiskiainen.org>

from yum.plugins import PluginYumExit
from yum.misc import unique
from yum.packages import YumInstalledPackage
from yum.plugins import TYPE_CORE

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)

knames = ['kernel', 'kernel-smp', 'kernel-hugemen']

def kunamer(kernel):
    ksuff = ""
    tmp = kernel.name.split('-')
    if len(tmp) > 1:
        ksuff = tmp[1]
    return "%s-%s%s" % (kernel.version, kernel.release, ksuff)

def find_kmodules(availpkgs, provides, kernels):
    matches = []
    for pkg in availpkgs:
        for kern in kernels:
            for prov in provides:
                if pkg.name == "%s-%s" % (prov, kunamer(kern)):
                    matches.append(pkg)
    return unique(matches)

def preresolve_hook(conduit):
    ts = conduit.getTsInfo()
    kernels = []
    for tsmem in ts.getMembers():
        if tsmem.ts_state == 'u' and tsmem.name in knames:
            kernels.append(tsmem.po)

    # pkgSack isn't populated on removals so this could traceback
    try:
        pkgs = conduit.getPackages()
    except AttributeError:
        return

    instpkgs = []
    for hdr in conduit.getRpmDB().getHdrList():
        po = YumInstalledPackage(hdr)
        instpkgs.append(po)

    kmodprovides = []
    for pkg in instpkgs:
        if pkg.name.startswith('kernel-module'):
            for prov in pkg.tagByName('providename'):
                kmodprovides.append(prov)

    mods = find_kmodules(pkgs, kmodprovides, kernels)
    for pkg in mods:
        conduit.info(2, 'Adding kernel module %s to transaction' % pkg.name)
        ts.addInstall(pkg)

# vim:ts=4:expandtab

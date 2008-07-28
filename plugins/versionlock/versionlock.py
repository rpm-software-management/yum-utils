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
#

from yum.plugins import PluginYumExit
from yum.plugins import TYPE_CORE
from rpmUtils.miscutils import splitFilename, compareEVR
import urlgrabber
import urlgrabber.grabber

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)

def vl_search(conduit, name):
    """ Search for packages with a particular name. """
    # Note that conduit.getPackageByNevra _almost_ works enough, but doesn't
    return conduit._base.pkgSack.searchNevra(name=name)

def exclude_hook(conduit):
    conduit.info(2, 'Reading version lock configuration')
    locklist = []
    location = conduit.confString('main', 'locklist')
    if not location:
        raise PluginYumExit('Locklist not set')
    try:
        llfile = urlgrabber.urlopen(location)
        for line in llfile.readlines():
            if line.startswith('#') or line.strip() == '':
                continue
            locklist.append(line.rstrip())
        llfile.close()
    except urlgrabber.grabber.URLGrabError, e:
        raise PluginYumExit('Unable to read version lock configuration: %s' % e)

    pkgs = {}
    for ent in locklist:
        (n, v, r, e, a) = splitFilename(ent)
        if e == '': 
            e = '0'
        pkgs.setdefault(n, []).append((e, v, r))

    if conduit.confBool('main', 'follow_obsoletes', default=False):
        #  If anything obsoletes something that we have versionlocked ... then
        # remove all traces of that too.
        obs = conduit._base.pkgSack.returnObsoletes()
        for ob in obs:
            for po in obs[ob]:
                if po.name not in pkgs:
                    continue
                # If anyone versions a pkg this, they need a good kicking
                pkgs.setdefault(ob[0], []).append(('0', '0', '0'))

    for pkgname in pkgs:
        for pkg in vl_search(conduit, pkgname):
            found = False
            for tup in pkgs[pkgname]:
                if not compareEVR((pkg.epoch, pkg.version, pkg.release), tup):
                    found = True
            if not found:
                conduit.delPackage(pkg)
                conduit.info(5, 'Excluding package %s due to version lock' % pkg)

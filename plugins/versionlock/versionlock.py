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

    pkgs = conduit.getPackages()
    locked = {}
    for pkg in locklist:
        (n, v, r, e, a) = splitFilename("%s" % pkg)
        if e == '': 
            e = '0'
        locked[n] = (e, v, r) 
    for pkg in pkgs:
        if locked.has_key(pkg.name):
            (n,a,e,v,r) = pkg.pkgtup
            if compareEVR(locked[pkg.name], (e, v, r)) != 0:
                conduit.delPackage(pkg)
                conduit.info(5, 'Excluding package %s due to version lock' % pkg)

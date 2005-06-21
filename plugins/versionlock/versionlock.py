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

from yum.constants import *
from yum.plugins import PluginYumExit
from rpmUtils.miscutils import splitFilename, compareEVR

requires_api_version = '2.1'

def config_hook(conduit):
    conduit.registerOpt('locklist', PLUG_OPT_STRING, PLUG_OPT_WHERE_MAIN, '')

def exclude_hook(conduit):
    conduit.info(2, 'Reading version lock configuration')
    locklist = []
    try:
        llfile = open(conduit.confString('main', 'locklist'))
        for line in llfile.readlines():
            locklist.append(line.rstrip())
        llfile.close()
    except IOError:
        raise PluginYumExit('Unable to read version lock configuration')

    pkgs = conduit.getPackages()
    locked = {}
    for pkg in locklist:
        # Arch doesn't matter but splitFilename wants it so fake it...
        (n, v, r, e, a) = splitFilename("%s.arch" % pkg)
        if e == '': 
            e = '0'
        locked[n] = (e, v, r) 
    for pkg in pkgs:
        if locked.has_key(pkg.name):
            (n, e, v, r, a) = pkg.returnNevraTuple()
            if compareEVR(locked[pkg.name], (e, v, r)) != 0:
                conduit.delPackage(pkg)
                conduit.info(5, 'Excluding package %s due to version lock' % pkg)

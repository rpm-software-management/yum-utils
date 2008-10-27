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
# by Ralf Ertzinger <ralf@skytale.net>
#
# This plugin reads the complete RPM database into the buffer cache
# in order to improve database reads later on.
# Don't use this if you're short on memory, anyways.

from yum.plugins import PluginYumExit, TYPE_CORE
from os import walk, path

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)

def postreposetup_hook(conduit):
    opts, commands = conduit.getCmdLine()
    if commands[0] in ('upgrade', 'install', 'remove'):
        try:
            for root, dirs, files in walk('/var/lib/rpm'):
                for file in files:
                    f = open(path.join(root, file))
                    d = f.read(1024*1024)
                    while(len(d) > 0):
                        d = f.read(1024*1024)
                    f.close()
        except:
            # Do nothing in case something fails, caching is entirely
            # optional.
            pass

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

requires_api_version = '2.1'

def init_hook(conduit):
    parser = conduit.getOptParser()
    parser.add_option('--tsflags', dest='tsflags')

def postreposetup_hook(conduit):
    opts, args = conduit.getCmdLine()
    conf = conduit.getConf()
    if opts.tsflags:
        flags = opts.tsflags.split(',')
        conf.setConfigOption('tsflags', flags)

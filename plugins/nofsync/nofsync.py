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

from yum.plugins import TYPE_INTERACTIVE
requires_api_version = '2.4'
plugin_type = (TYPE_INTERACTIVE,)

def init_hook(conduit):
    parser = conduit.getOptParser()
    if parser:
        if hasattr(parser, 'plugin_option_group'):
            parser = parser.plugin_option_group
        parser.add_option('--nofsync', dest='nofsync',
               default=False, action='store_true',
               help='Disable database syncing during transaction (DANGEROUS)')

def pretrans_hook(conduit):
    opts, args = conduit.getCmdLine()
    if opts and opts.nofsync:
        import rpm
        dbconf = rpm.expandMacro('%{_dbi_config_Packages} nofsync')
        rpm.addMacro('_dbi_config_Packages', dbconf)

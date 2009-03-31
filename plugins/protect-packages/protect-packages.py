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


# Copyright 2007 Boston University 
# written by Svetlana Anissimova <svetanis@gmail.com> and
#            Matthew Miller <mattdm@mattdm.org>

"""
This plugin prevents Yum from removing itself and other protected packages.

By default, yum is the only package protected, but by extension this
automatically protects everything on which yum depends (rpm, python, glibc, 
and so on).Therefore, the plugin functions well even without
compiling careful lists of all important packages.

Additional packages to protect may be listed one per line in the file
/etc/sysconfig/protected-packages and in *.list files placed in  
/etc/sysconfig/protected-packages.d/. 

If you wish to temporarily exclude certain packages from protection, you can
use the --override-protection command-line option. 
"""


from yum.plugins import TYPE_CORE, TYPE_INTERACTIVE, PluginYumExit
import os
import string
import glob

requires_api_version = '2.4'
plugin_type = (TYPE_CORE, TYPE_INTERACTIVE)

def config_hook(conduit):
    parser = conduit.getOptParser()
    if hasattr(parser, 'plugin_option_group'):
        parser = parser.plugin_option_group
    parser.add_option("", "--override-protection", dest='override', 
                      action="append", default=[], metavar='[package]',
                      help="remove package from the list of protected packages")

def postresolve_hook(conduit):
    protectedpkgs = ['yum']
    protectedlist = []
    opts, args = conduit.getCmdLine()

    confdir = conduit.confString('main','confdir','/etc/sysconfig')

    if os.access(confdir + "/protected-packages", os.R_OK) : 
        protectedlist.append(confdir + "/protected-packages")

    if os.access(confdir + "/protected-packages.d", os.R_OK):
        protectedlist.extend(glob.glob(confdir + "/protected-packages.d/*.list"))

    if protectedlist:
        for f in protectedlist:
            for line in open(f).readlines():            
                line = string.strip(line)
                if (line and line[0] != "#" and line not in opts.override  
                                            and line not in protectedpkgs):
                    protectedpkgs.append(line)

    for tsmem in conduit.getTsInfo().getMembers():
        if tsmem.name in protectedpkgs and tsmem.ts_state == 'e':
            raise PluginYumExit("This transaction would cause %s to be removed."
                " This package is vital for the basic operation of your system."
                " If you really want to remove it, edit the list of protected"
                " packages in the file %s or in the directory %s or use the"
                " --override-protection command-line option."
                %(tsmem.name, confdir + "/protected-packages",
                 confdir + "/protected-packages.d"))







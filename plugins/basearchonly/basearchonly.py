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
# Copyright 2007 by Adel Gadllah

import re, os
from fnmatch import fnmatch
from yum.plugins import TYPE_INTERACTIVE

requires_api_version = '2.3'
plugin_type = TYPE_INTERACTIVE


def exclude_hook(conduit):

	""" Only install i386 packages when told to do so """
	if os.uname()[-1] == 'x86_64':
		basearch(conduit, "x86", "i?86$")
	
	""" Only install ppc64 packages when told to do so """	
	if os.uname()[-1] == 'ppc64':
		basearch(conduit, "ppc", "ppc64$")

	""" Only install sparc64 packages when told to do so """	
	if os.uname()[-1] == 'sparc64':
		basearch(conduit, "sparc", "sparc64$")


def basearch(conduit, barch, excludearchP):
	
	exclude = []
	whitelist = []
	skippkg = 0
	conf , cmd = conduit.getCmdLine()
	packageList = conduit.getPackages()
	excludearch = re.compile(excludearchP);
	
	if not cmd:
		return

	if cmd[0] != "install":
		return

	""" get whitelist from config file """	
	
	conflist = conduit.confString(barch, 'whitelist')
	if conflist:
		tmp = conflist.split(",")
		for confitem in tmp:
			whitelist.append(confitem.strip())
	
	""" decide which packages we want to exclude """	

	for userpkg in cmd:
          skippkg = 0
          for wlpkg in whitelist:
               if fnmatch(userpkg,wlpkg):
                 skippkg = 1
          if not skippkg and not excludearch.search(userpkg):
            exclude.append(userpkg)

	""" exclude the packages """	
	
	for pkg in packageList:
		if pkg.name in exclude and excludearch.search(pkg.arch):
			conduit.delPackage(pkg)
			conduit.info(3, "--> excluded %s.%s" % (pkg.name, pkg.arch))	


#! /usr/bin/python -tt
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
#
# Copyright Red Hat Inc. 2007, 2008
#
# Author: James Antill <james.antill@redhat.com>
#
# Examples:
#
#  yum list-vendors
#  yum list-packagers yum*
#  yum list-groups updates


import yum
import types
from yum.plugins import TYPE_INTERACTIVE
import logging # for commands
from yum import logginglevels

# For baseurl
import urlparse

# Decent (UK/US English only) number formatting.
import locale
locale.setlocale(locale.LC_ALL, '') 

def loc_num(x):
    """ Return a string of a number in the readable "locale" format. """
    return locale.format("%d", int(x), True)

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)

class ListDataCommands:
    unknown = "-- Unknown --"
    
    def __init__(self, name, attr):
        self.name = name
        self.attr = attr

    def getNames(self):
        return ['list-' + self.name]

    def getUsage(self):
        return self.getNames()[0]

    def doCheck(self, base, basecmd, extcmds):
        pass

    def show_pkgs(self, msg, pkgs):
        pass

    def show_data(self, msg, pkgs, name):
        if not pkgs:
            return
        msg("%s %s %s" % ('=' * 20, name, '=' * 20))
        pkgs.sort(key=lambda x: x.name)
        calc = {}
        for pkg in pkgs:
            data = self.get_data(pkg)
            calc.setdefault(data, []).append(pkg)
        maxlen = 0
        totlen = 0
        for data in calc:
            val = len(data)
            totlen += len(calc[data])
            if val > maxlen:
                maxlen = val
        fmt = "%%-%ds %%6s (%%3d%%%%)" % maxlen
        for data in sorted(calc):
            val = len(calc[data])
            msg(fmt % (str(data), loc_num(val), (100 * val) / totlen))
            self.show_pkgs(msg, calc[data])

    # pkg.vendor has weird values, for instance
    def get_data(self, data):
        if not hasattr(data, self.attr):
            return self.unknown
        
        val = getattr(data, self.attr)
        if val is None:
            return self.unknown
        if type(val) == type([]):
            return self.unknown

        tval = str(val).strip()
        if tval == "":
            return self.unknown
        
        return val
            
    def doCommand(self, base, basecmd, extcmds):
        logger = logging.getLogger("yum.verbose.main")
        def msg(x):
            logger.log(logginglevels.INFO_2, x)
        def msg_warn(x):
            logger.warn(x)

        ypl = base.returnPkgLists(extcmds)
        self.show_data(msg, ypl.installed, 'Installed Packages')
        self.show_data(msg, ypl.available, 'Available Packages')
        self.show_data(msg, ypl.extras,    'Extra Packages')
        self.show_data(msg, ypl.updates,   'Updated Packages')
        self.show_data(msg, ypl.obsoletes, 'Obsoleting Packages')

        return 0, [basecmd + ' done']
            
class InfoDataCommands(ListDataCommands):
    def getNames(self):
        return ['info-' + self.name]

    def show_pkgs(self, msg, pkgs):
        for pkg in pkgs:
            msg("    %s" % (pkg))

def url_get_data(self, data): # Special version for baseurl
    val = self.oget_data(data)
    if val == self.unknown:
        return val
    (scheme, netloc, path, query, fragid) = urlparse.urlsplit(val)
    return "%s://%s/" % (scheme, netloc)

class SizeRangeData:
    def __init__(self, beg, msg):
        self._beg = beg
        self._msg = msg

    def __cmp__(self, o):
        if not hasattr(o, '_beg'):
            return 1
        return cmp(self._beg, o._beg)
    
    def __str__(self):
        return self._msg
    
    def __len__(self):
        return len(self._msg)

    def __hash__(self):
        return hash(self._msg)

def size_get_data(self, data):
    val = self.oget_data(data)
    if val == self.unknown:
        return val

    #  Even if it was sane, don't put 1GB and up here, or the alpha sorting
    # won't be correct.
    nums = (( 10 * 1024,        " 10KB"),
            ( 25 * 1024,        " 25KB"),
            ( 50 * 1024,        " 50KB"),
            ( 75 * 1024,        " 75KB"),
            (100 * 1024,        "100KB"),
            (250 * 1024,        "250KB"),
            (500 * 1024,        "500KB"),
            (750 * 1024,        "750KB"),
            (  1 * 1024 * 1024, "  1MB"),
            (  5 * 1024 * 1024, "  5MB"),
            ( 10 * 1024 * 1024, " 10MB"),
            ( 50 * 1024 * 1024, " 50MB"),
            (100 * 1024 * 1024, "100MB"),
            (500 * 1024 * 1024, "500MB"),
            )
    pnum = (0, "  0KB")
    for num in nums:
        if val >= pnum[0] and val <= num[0]:
            msg = "[ %s - %s ]  " % (pnum[1], num[1])
            return SizeRangeData(pnum[0], msg)
        pnum = num
    msg = "[ %s - %s ]  " % (pnum[1], " " * len(pnum[1]))
    return SizeRangeData(pnum[0], msg)    

def _list_data_custom(conduit, data, func):
    cmd = ListDataCommands(*data)
    cmd.oget_data = cmd.get_data 
    cmd.get_data  = types.MethodType(func, cmd)
    conduit.registerCommand(cmd)

    cmd = InfoDataCommands(*data)
    cmd.oget_data = cmd.get_data 
    cmd.get_data  = types.MethodType(func, cmd)
    conduit.registerCommand(cmd)
    
        
def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Add the 'list-vendors', 'list-baseurls', 'list-packagers',
    'list-buildhosts' commands and the info varients.
    '''

    for data in [('vendors', 'vendor'),
                 ('groups', 'group'),
                 ('packagers', 'packager'),
                 ('licenses', 'license'),
                 ('arches', 'arch'),
                 ('committers', 'committer'),
                 ('buildhosts', 'buildhost')]:
        conduit.registerCommand(ListDataCommands(*data))
        conduit.registerCommand(InfoDataCommands(*data))

    _list_data_custom(conduit, ('baseurls', 'url'), url_get_data)
    _list_data_custom(conduit, ('package-sizes', 'packagesize'), size_get_data)
    _list_data_custom(conduit, ('archive-sizes', 'archivesize'), size_get_data)
    _list_data_custom(conduit, ('installed-sizes', 'installedsize'),
                      size_get_data)
    
    # Buildtime/installtime/committime?

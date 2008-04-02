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

    def cmd_beg(self):
        pass

    def cmd_end(self):
        pass

    def getNames(self):
        return ['list-' + self.name]

    def getUsage(self):
        return "[PACKAGE|all|installed|updates|extras|obsoletes|recent]"

    def _getSummary(self):
        return """\
Display aggregate data on the %s attribute of a group of packages""" % self.attr

    def getSummary(self):
        return self._getSummary()

    def doCheck(self, base, basecmd, extcmds):
        pass

    def show_pkgs(self, msg, gval, pkgs):
        pass

    def show_data(self, msg, pkgs, name):
        if not pkgs:
            return
        msg("%s %s %s" % ('=' * 20, name, '=' * 20))
        pkgs.sort(key=lambda x: x.name)
        calc = {}
        for pkg in pkgs:
            (data, rdata) = self.get_data(pkg)
            if type(data) != type([]):
                calc.setdefault(data, []).append((pkg, rdata))
            else:
                for sdata in data:
                    calc.setdefault(sdata, []).append((pkg, rdata))
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
            self.show_pkgs(msg, data, calc[data])

    # pkg.vendor has weird values, for instance
    def get_data(self, data, strip=True):
        if not hasattr(data, self.attr):
            return (self.unknown, self.unknown)
        
        val = getattr(data, self.attr)
        if val is None:
            return self.unknown
        if type(val) == type([]):
            return (self.unknown, self.unknown)

        tval = str(val).strip()
        if tval == "":
            return (self.unknown, self.unknown)

        if strip:
            return (tval, tval)

        return (val, val)
            
    def doCommand(self, base, basecmd, extcmds):
        self.base = base
        
        logger = logging.getLogger("yum.verbose.main")
        def msg(x):
            logger.log(logginglevels.INFO_2, x)
        def msg_warn(x):
            logger.warn(x)

        self.cmd_beg()
        ypl = base.returnPkgLists(extcmds)
        self.show_data(msg, ypl.installed, 'Installed Packages')
        self.show_data(msg, ypl.available, 'Available Packages')
        self.show_data(msg, ypl.extras,    'Extra Packages')
        self.show_data(msg, ypl.updates,   'Updated Packages')
        self.show_data(msg, ypl.obsoletes, 'Obsoleting Packages')
        self.show_data(msg, ypl.recent,    'Recent Packages')
        self.cmd_end()

        return 0, [basecmd + ' done']

    def needTs(self, base, basecmd, extcmds):
        if len(extcmds) and extcmds[0] == 'installed':
            return False
        
        return True

            
class InfoDataCommands(ListDataCommands):
    def getNames(self):
        return ['info-' + self.name]

    def getSummary(self):
        return self._getSummary() + "\nAnd list all the packages under each"

    def show_pkgs(self, msg, gval, pkgs):
        for (pkg, val) in pkgs:
            if gval == val:
                msg("  %s" % pkg)
                continue

            if type(val) == type([]):
                val = ", ".join(sorted(val))
            linelen = len(val) + len(str(pkg))
            if linelen < 77:
                msg("  %s %*s%s" % (pkg, 77 - linelen, '', val))
            else:
                msg("  %s" % pkg)
                msg("  => %s" % val)
                msg('')
        if pkgs:
            msg('')

def buildhost_get_data(self, data): # Just show the dnsname
    val = self.oget_data(data)[0]
    if val == self.unknown:
        return (val, val)
    dns_names = val.split('.')
    if len(dns_names) > 2:
        dns_names[0] = '*'
    return (".".join(dns_names), val)

def url_get_data(self, data): # Just show the hostname
    val = self.oget_data(data)[0]
    if val == self.unknown:
        return (val, val)
    (scheme, netloc, path, query, fragid) = urlparse.urlsplit(val)
    return ("%s://%s/" % (scheme, netloc), val)

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

def _format_size(base, num, max):
    return "%s (%*s)" %(base.format_number(num),len(loc_num(max)),loc_num(num))

def size_get_data(self, data):
    val = self.oget_data(data, strip=False)[0]
    if val == self.unknown:
        return (val, val)

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
    pnum = (0, "   0B")
    if val <= pnum[0]:
        msg = "[ %s - %s ]  " % (" " * len(pnum[1]), pnum[1])
        return (SizeRangeData(pnum[0], msg),
                _format_size(self.base, val, pnum[0]))

    pnum = (1, "   1B")
    for num in nums:
        if val >= pnum[0] and val <= num[0]:
            msg = "[ %s - %s ]  " % (pnum[1], num[1])
            return (SizeRangeData(pnum[0], msg),
                    _format_size(self.base, val, num[0]))
        pnum = num
    msg = "[ %s - %s ]  " % (pnum[1], " " * len(pnum[1]))
    return (SizeRangeData(pnum[0], msg),
            _format_size(self.base, val, pnum[0] * 20))


all_yum_grp_mbrs = {}
def yum_group_make_data(self):
    global all_yum_grp_mbrs

    base = self.attr
    installed, available = base.doGroupLists(uservisible=0)
    for group in installed + available:

        # Should use translated_name/nameByLang()
        for pkgname in group.mandatory_packages:
            all_yum_grp_mbrs.setdefault(pkgname, []).append(group.name)
        for pkgname in group.default_packages:
            all_yum_grp_mbrs.setdefault(pkgname, []).append(group.name)
        for pkgname in group.optional_packages:
            all_yum_grp_mbrs.setdefault(pkgname, []).append(group.name)
        for pkgname, cond in group.conditional_packages.iteritems():
            all_yum_grp_mbrs.setdefault(pkgname, []).append(group.name)

def yum_group_free_data(self):
    global all_yum_grp_mbrs
    all_yum_grp_mbrs = {}

def yum_group_get_data(self, pkg):
    if pkg.name not in all_yum_grp_mbrs:
        return (self.unknown, self.unknown)
    return (all_yum_grp_mbrs[pkg.name], all_yum_grp_mbrs[pkg.name])

def _list_data_custom(conduit, data, func, beg=None, end=None):
    cmd = ListDataCommands(*data)
    cmd.oget_data = cmd.get_data 
    cmd.get_data  = types.MethodType(func, cmd)
    if beg:
        cmd.cmd_beg = types.MethodType(beg, cmd)
    if end:
        cmd.cmd_end = types.MethodType(end, cmd)
    conduit.registerCommand(cmd)

    cmd = InfoDataCommands(*data)
    cmd.oget_data = cmd.get_data 
    cmd.get_data  = types.MethodType(func, cmd)
    if beg:
        cmd.cmd_beg = types.MethodType(beg, cmd)
    if end:
        cmd.cmd_end = types.MethodType(end, cmd)
    conduit.registerCommand(cmd)
    
        
def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Add the 'list-vendors', 'list-baseurls', 'list-packagers',
    'list-buildhosts' commands and the info varients.
    '''

    for data in [('vendors', 'vendor'),
                 ('rpm-groups', 'group'),
                 ('packagers', 'packager'),
                 ('licenses', 'license'),
                 ('arches', 'arch'),
                 ('committers', 'committer')]:
        conduit.registerCommand(ListDataCommands(*data))
        conduit.registerCommand(InfoDataCommands(*data))

    _list_data_custom(conduit, ('buildhosts', 'buildhost'), buildhost_get_data)
    _list_data_custom(conduit, ('baseurls', 'url'), url_get_data)
    _list_data_custom(conduit, ('package-sizes', 'packagesize'), size_get_data)
    _list_data_custom(conduit, ('archive-sizes', 'archivesize'), size_get_data)
    _list_data_custom(conduit, ('installed-sizes', 'installedsize'),
                      size_get_data)
    
    _list_data_custom(conduit, ('groups', conduit._base),
                      yum_group_get_data,
                      beg=yum_group_make_data, end=yum_group_free_data)
    
    # Buildtime/installtime/committime?

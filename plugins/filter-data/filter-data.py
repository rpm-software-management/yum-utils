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
#  This is the compliment to the list-data plugin, allowing you to filter on
# any of the information given in that plugin.
#
# Examples:
#
#  yum --filter-groups='App*/Sys*' list updates

import yum
from yum.plugins import TYPE_INTERACTIVE

import fnmatch

# For baseurl
import urlparse


requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)


fd__unknown = lambda x: x
fd__max     = 9999999999999
def fd__get_data(pkg, attr, strip=True):
    if not hasattr(pkg, attr):
        return fd__unknown

    val = getattr(pkg, attr)
    if val is None:
        return fd__unknown
    if type(val) == type([]):
        return fd__unknown

    tval = str(val).strip()
    if tval == "":
        return fd__unknown

    if strip:
        return tval

    return val

def range_match(sz, rang):
    return sz >= rang[0] and sz <= rang[1]

all_yum_grp_mbrs = {}
def fd_make_group_data(base, opts):
    global all_yum_grp_mbrs

    for pat in opts.filter_groups:

        group = base.comps.return_group(pat)
        if not group:
            base.logger.critical('Warning: Group %s does not exist.', pat)
            continue

        for pkgname in group.mandatory_packages:
            all_yum_grp_mbrs.setdefault(pkgname, []).append(pat)
        for pkgname in group.default_packages:
            all_yum_grp_mbrs.setdefault(pkgname, []).append(pat)
        for pkgname in group.optional_packages:
            all_yum_grp_mbrs.setdefault(pkgname, []).append(pat)
        for pkgname, cond in group.conditional_packages.iteritems():
            all_yum_grp_mbrs.setdefault(pkgname, []).append(pat)

def fd_free_group_data():
    global all_yum_grp_mbrs
    all_yum_grp_mbrs = {}

def fd_should_filter_pkg(base, opts, pkg, used_map):
    """ Do the package filtering for. """

    for (attrs, attr) in [('vendors', 'vendor'),
                          ('rpm-groups', 'group'),
                          ('packagers', 'packager'),
                          ('licenses', 'license'),
                          ('arches', 'arch'),
                          ('committers', 'committer'),
                          ('buildhosts', 'buildhost'),
                          ('urls', 'url')]:
        pats = getattr(opts, 'filter_' + attrs.replace('-', '_'))
        filt = len(pats)
        data = fd__get_data(pkg, attr)
        for pat in pats:
            if data == fd__unknown or fnmatch.fnmatch(data, pat):
                used_map[attrs][pat] = True
                filt = False
                break
        if filt:
            return (attrs, attr)

    for (attrs, attr) in [('package-sizes', 'packagesize'),
                          ('archive-sizes', 'archivesize'),
                          ('installed-sizes', 'installedsize')]:
        rangs = getattr(opts, 'filter_' + attrs.replace('-', '_'))
        filt = len(rangs)
        data = fd__get_data(pkg, attr, strip=False)
        for rang in rangs:
            if data == fd__unknown or range_match(data, rang):
                used_map[attrs][rang] = True
                filt = False
                break
        if filt:
            return (attrs, attr)

    if len(opts.filter_groups):
        if pkg.name not in all_yum_grp_mbrs:
            return ('groups', None)

        for pat in all_yum_grp_mbrs[pkg.name]:
            used_map['groups'][pat] = True
            break

    return None

def fd_gen_used_map(opts):
    used_map = {}
    for (attrs, attr) in [('vendors', 'vendor'),
                          ('rpm-groups', 'group'),
                          ('packagers', 'packager'),
                          ('licenses', 'license'),
                          ('arches', 'arch'),
                          ('committers', 'committer'),
                          ('buildhosts', 'buildhost'),
                          ('urls', 'url'),
                          ('package-sizes', 'packagesize'),
                          ('archive-sizes', 'archivesize'),
                          ('installed-sizes', 'installedsize'),
                          ('groups', None)]:
        used_map[attrs] = {}
        vattrs = attrs.replace('-', '_')
        for i in getattr(opts, 'filter_' + vattrs):
            used_map[attrs][i] = False

    return used_map

def fd_chk_used_map(used_map, msg):
    for (attrs, attr) in [('vendors', 'vendor'),
                          ('rpm-groups', 'rpm group'),
                          ('packagers', 'packager'),
                          ('licenses', 'license'),
                          ('arches', 'arch'),
                          ('committers', 'committer'),
                          ('buildhosts', 'buildhost'),
                          ('urls', 'url')]:
        for i in used_map[attrs]:
            if not used_map[attrs][i]:
                msg(attr.capitalize() +
                    ' wildcard \"%s\" did not match any packages' % i)

    for (attrs, attr) in [('package-sizes', 'packagesize'),
                          ('archive-sizes', 'archivesize'),
                          ('installed-sizes', 'installedsize')]:
        for i in used_map[attrs]:
            if not used_map[attrs][i]:
                if i[1] == fd__max:
                    msg(attrs[:-1].capitalize() +
                        ' range \"%d-\" did not match any packages' % i[0])
                else:
                    msg(attrs[:-1].capitalize() +
                        ' range \"%d-%d\" did not match any packages' % i)

    for i in used_map['groups']:
        if not used_map['groups'][i]:
            msg('Yum group \"%s\" did not contain any packages' % i)

        
#  You might think we'd just use the exclude_hook, and call delPackage
# and indeed that works for list updates etc.
#
# __but__ that doesn't work for dependancies on real updates
#
#  So to fix deps. we need to do it at the preresolve stage and take the
# "transaction package list" and then remove packages from that.
#
# __but__ that doesn't work for lists ... so we do it two ways
#
def fd_check_func_enter(conduit):
    """ Stuff we need to do in both list and update modes. """
    
    opts, args = conduit.getCmdLine()

    # Quick match, so we don't do lots of work when nothing has been specified
    ndata = True
    for (attrs, attr) in [('vendors', 'vendor'),
                          ('rpm-groups', 'group'),
                          ('packagers', 'packager'),
                          ('licenses', 'license'),
                          ('arches', 'arch'),
                          ('committers', 'committer'),
                          ('buildhosts', 'buildhost'),
                          ('urls', 'url'),
                          ('package-sizes', 'packagesize'),
                          ('archive-sizes', 'archivesize'),
                          ('installed-sizes', 'installedsize')]:
        vattrs = attrs.replace('-', '_')
        if len(getattr(opts, 'filter_' + vattrs)):
            ndata = False
    if len(opts.filter_groups):
        ndata = False
    
    ret = None
    if len(args) >= 1:
        if (args[0] in ["update", "upgrade", "install"]):
            ret = {"skip": ndata, "list_cmd": False}
        if (args[0] in ["check-update"]): # Pretend it's: list updates
            ret = {"skip": ndata, "list_cmd": True,
                   "ret_pkg_lists": ["updates"] + args[1:]}

    # FIXME: delPackage() only works for updates atm.
    valid_list_cmds = ["list", "info"]
    for cmd in ["vendors", 'rpm-groups', 'packagers', 'licenses', 'arches',
                'committers', 'buildhosts', 'baseurls', 'package-sizes',
                'archive-sizes', 'installed-sizes', 'security', 'sec',
                'groups']:
        valid_list_cmds.append("list-" + cmd)
        valid_list_cmds.append("info-" + cmd)

    if (len(args) >= 2 and args[0] in valid_list_cmds and args[1] == "updates"):
        ret = {"skip": ndata, "list_cmd": True, "ret_pkg_lists": args[1:]}

    if ret:
        if ndata:
            conduit.info(2, 'Skipping filters plugin, no data')
        return (opts, ret)
    
    if not ndata:
        conduit.error(2, 'Skipping filters plugin, other command')
    return (opts, {"skip": True, "list_cmd": False, "msg": True})


_in_plugin = False
def exclude_hook(conduit):
    '''
    Yum Plugin Exclude Hook:
    Check and remove packages that don\'t align with the filters.
    '''

    global _in_plugin
    
    opts, info = fd_check_func_enter(conduit)
    if info["skip"]:
        return

    if not info["list_cmd"]:
        return

    if _in_plugin:
        return
    
    _in_plugin = True
    conduit.info(2, 'Limiting package lists to filtered ones')
    
    def fd_del_pkg(pkg, which):
        """ Deletes a package from all trees that yum knows about """
        conduit.info(3," --> %s from %s excluded (filter: %s)" %
                     (pkg, pkg.repoid, which[0]))
        conduit.delPackage(pkg)

    used_map = fd_gen_used_map(opts)

    # NOTE: excludes/delPackage() doesn't work atm. for non-"list upgrades"
    if not info['ret_pkg_lists']:
        pkgs = conduit.getPackages()
    else:
        args = info['ret_pkg_lists']
        special = ['updates']
        pn = None
        pkgs = []
        if len(args) >= 1 and args[0] in special:
            pn = args[0]
            args = args[1:]
        else:
            pkgs = conduit.getPackages()

        if not len(args):
            args = None
        if pn:
            data = conduit._base.doPackageLists(pkgnarrow=pn, patterns=args)
            pkgs.extend(data.updates)
            del data

    if opts.filter_groups:
        fd_make_group_data(conduit._base, opts)
    tot = 0
    cnt = 0
    for pkg in pkgs:
        tot += 1
        which = fd_should_filter_pkg(conduit._base, opts, pkg, used_map)
        if which:
            fd_del_pkg(pkg, which)
        else:
            cnt += 1
    fd_chk_used_map(used_map, lambda x: conduit.error(2, x))
    if cnt:
        conduit.info(2, 'Left with %d of %d packages, after filters applied' % (cnt, tot))
    else:
        conduit.info(2, 'No packages passed the filters, %d available' % tot)

    fd_free_group_data()
    _in_plugin = False

def preresolve_hook(conduit):
    '''
    Yum Plugin PreResolve Hook:
    Check and remove packages that don\'t align with the filters.
    '''

    opts, info = fd_check_func_enter(conduit)
    if info["skip"]:
        return

    if info["list_cmd"]:
        return
    
    conduit.info(2, 'Limiting package lists to filtered ones')

    def fd_del_pkg(tspkg, which):
        """ Deletes a package within a transaction. """
        conduit.info(3," --> %s from %s excluded (filter: %s)" %
                     (tspkg.po, tspkg.po.repoid, which[0]))
        tsinfo.remove(tspkg.pkgtup)

    if opts.filter_groups:
        fd_make_group_data(conduit._base, opts)
    tot = 0
    cnt = 0
    used_map = fd_gen_used_map(opts)
    tsinfo = conduit.getTsInfo()
    tspkgs = tsinfo.getMembers()
    for tspkg in tspkgs:
        tot += 1
        which = fd_should_filter_pkg(conduit._base, opts, tspkg.po, used_map)
        if which:
            fd_del_pkg(tspkg, which)
        else:
            cnt += 1
    fd_chk_used_map(used_map, lambda x: conduit.error(2, x))
    
    if cnt:
        conduit.info(2, 'Left with %d of %d packages, after filters applied' % (cnt, tot))
    else:
        conduit.info(2, 'No packages passed the filters, %d available' % tot)
    fd_free_group_data()

def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Setup the option parser with the '--filter-*' command line options.
    '''

    parser = conduit.getOptParser()
    if not parser:
        return

    parser.values.filter_vendors         = []
    parser.values.filter_rpm_groups      = []
    parser.values.filter_packagers       = []
    parser.values.filter_licenses        = []
    parser.values.filter_arches          = []
    parser.values.filter_committers      = []
    parser.values.filter_buildhosts      = []
    parser.values.filter_urls            = []
    parser.values.filter_packages_sizes  = []
    parser.values.filter_archive_sizes   = []
    parser.values.filter_installed_sizes = []
    parser.values.filter_groups          = []
    def make_sopt(attrs):
        attrs = attrs.replace("-", "_")
        def func(opt, key, val, parser):
            vals = str(val).split(",")
            vals = filter(len, vals)
            getattr(parser.values, 'filter_' + attrs).extend(vals)
        return func
    def make_nopt(attrs):
        attrs = attrs.replace("-", "_")
        def func(opt, key, val, parser):
            vals = str(val).replace(",", " ").split()
            vals = filter(len, vals)
            getattr(parser.values, 'filter_' + attrs).extend(vals)
        return func
    def make_szopt(attrs):
        attrs = attrs.replace("-", "_")
        def func(opt, key, val, parser):
            def sz_int(x, empty_sz):
                if x == '':
                    return empty_sz
                mul = 1
                conv = {'k' : 1024, 'm' : 1024 * 1024, 'g' : 1024 * 1024 * 1024}
                if x[-1].lower() in conv:
                    mul = conv[x[-1]]
                    x = x[:-1]
                return int(x) * mul
            vals = str(val).replace(",", " ").split()
            vals = filter(len, vals)
            for val in vals:
                rang = val.split("-")
                if len(rang) > 2:
                    msg = "%s was passed an invalid range: %s" % (attrs, val)
                    raise OptionValueError, msg
                if len(rang) < 2:
                    rang = (rang[0], rang[0])
                else:
                    rang = (sz_int(rang[0], 0), sz_int(rang[1], fd__max))

                getattr(parser.values, 'filter_' + attrs).append(rang)
        return func

    # These have spaces in their values, so we can't split on space
    for (attrs, attr) in [('vendors', 'vendor'),
                          ('rpm-groups', 'group'),
                          ('packagers', 'packager'),
                          ('licenses', 'license'),
                          ('committers', 'committer')]:
        parser.add_option('--filter-' + attrs, action="callback",
                          callback=make_sopt(attrs), default=[], type="string",
                          help='Filter to packages with a matching ' + attr)

    for (attrs, attr) in [('arches', 'arch'),
                          ('buildhosts', 'buildhost'),
                          ('urls', 'url')]:
        parser.add_option('--filter-' + attrs, action="callback",
                          callback=make_nopt(attrs), default=[], type="string",
                          help='Filter to packages with a matching ' + attr)

    for (attrs, attr) in [('package-sizes', 'packagesize'),
                          ('archive-sizes', 'archivesize'),
                          ('installed-sizes', 'installedsize')]:
        parser.add_option('--filter-' + attrs, action="callback",
                          callback=make_szopt(attrs), default=[], type="string",
                          help='Filter to packages with a %s in the given range'
                          % attr)

    # This is kind of odd man out, but...
    parser.add_option('--filter-groups', action="callback",
                      callback=make_sopt('groups'),default=[],type="string",
                      help='Filter to packages within a matching yum group')

if __name__ == '__main__':
    print "This is a plugin that is supposed to run from inside YUM"

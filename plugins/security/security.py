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
# Copyright Red Hat Inc. 2007
#
# Author: James Antill <james.antill@redhat.com>
#
# Examples:
#
#  yum --security info updates
#  yum --security list updates
#  yum --security check-update
#  yum --security update
#
# yum --cve CVE-2007-1667      <cmd>
# yum --bz  235374 --bz 234688 <cmd>
# yum --advisory FEDORA-2007-420 --advisory FEDORA-2007-346 <cmd>
#
# yum sec-list
# yum sec-list bugzillas / bzs
# yum sec-list cves
# yum sec-list security / sec

import yum
import time
import textwrap
import fnmatch
import sys
from yum.plugins import TYPE_INTERACTIVE
from yum.update_md import UpdateMetadata
from rpmUtils.miscutils import compareEVR
import logging # for commands
from yum import logginglevels

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)

def ysp_gen_metadata(conduit):
    """ Generate the info. from the updateinfo.xml files. """
    md_info = UpdateMetadata()
    for repo in conduit.getRepos().listEnabled():
        if not repo.enabled:
            continue
        
        try: # attempt to grab the updateinfo.xml.gz from the repodata
            md_info.add(repo)
        except yum.Errors.RepoMDError:
            continue # No metadata found for this repo
    return md_info

def ysp__safe_refs(refs):
    """ Sometimes refs == None, if so return the empty list here. 
        So we don't have to check everywhere. """
    if refs == None:
        return []
    return refs

def ysp_should_filter_pkg(opts, pkg, md, used_map):
    """ Do the package filtering for should_show and should_keep. """
    
    def has_id(refs, ref_type, ref_ids):
        ''' Check if the given ID is a match. '''
        for ref in ysp__safe_refs(refs):
            if ref['type'] != ref_type:
                continue
            if ref['id'] not in ref_ids:
                continue
            used_map[ref_type][ref['id']] = True
            return ref
        return None
    def match_sec_cmd(sec_cmds, pkg, md):
        for i in sec_cmds:
            if fnmatch.fnmatch(pkg.name, i):
                return i
            if md['update_id'] == i:
                return i
        return None
    
    rcmd = match_sec_cmd(opts.sec_cmds, pkg, md)
    if rcmd:
        used_map['cmd'][rcmd] = True
        return md        
    elif opts.advisory and md['update_id'] in opts.advisory:
        used_map['id'][md['update_id']] = True
        return md
    elif opts.cve and has_id(md['references'], "cve", opts.cve):
        return md
    elif opts.bz and has_id(md['references'], "bugzilla", opts.bz):
        return md
    elif opts.security:
        if md['type'] == 'security':
            return md
    elif not (opts.advisory or opts.cve or opts.bz or opts.security or \
              opts.sec_cmds):
        return md # This is only possible from should_show_pkg
    return None

def ysp_has_info_md(rname, md):
    if rname == "security":
        if md['type'] == 'security':
            return md
    for ref in ysp__safe_refs(md['references']):
        if ref['type'] != rname:
            continue
        return md

def ysp_should_show_pkg(opts, pkg, md, used_map, rname=None):
    """ Do we want to show this package in list-security. """
    
    md = md.get_notice((pkg.name, pkg.ver, pkg.rel))
    if not md:
        return None

    if rname and not ysp_has_info_md(rname, md):
        return None
    return ysp_should_filter_pkg(opts, pkg, md, used_map)

def ysp_gen_used_map(opts):
    used_map = {'bugzilla' : {}, 'cve' : {}, 'id' : {}, 'cmd' : {}}
    for i in opts.sec_cmds:
        used_map['cmd'][i] = False
    for i in opts.advisory:
        used_map['id'][i] = False
    for i in opts.bz:
        used_map['bugzilla'][i] = False
    for i in opts.cve:
        used_map['cve'][i] = False
    return used_map

def ysp_chk_used_map(used_map, msg):
    for i in used_map['cmd']:
        if not used_map['cmd'][i]:
            msg('Argument \"%s\" not found applicable for this system' % i)
    for i in used_map['id']:
        if not used_map['id'][i]:
            msg('Advisory \"%s\" not found applicable for this system' % i)
    for i in used_map['bugzilla']:
        if not used_map['bugzilla'][i]:
            msg('BZ \"%s\" not found applicable for this system' % i)
    for i in used_map['cve']:
        if not used_map['cve'][i]:
            msg('CVE \"%s\" not found applicable for this system' % i)

class SecurityListCommands:
    def getNames(self):
        return ['list-security', 'list-sec']

    def getUsage(self):
        return "[security|bugzilla|cve] [PACKAGE-wildcard]"

    def getSummary(self):
        return "Returns security data for the packages listed, that affects your system"

    def doCheck(self, base, basecmd, extcmds):
        pass

    def getRepos(self): # so we can act as a "conduit"
        return self.repos

    def show_pkg(self, msg, pkg, md, disp=None):
        # Make the list view much smaller
        # ysp_show_pkg_md_info(pkg, md, msg)
        if disp and ysp_has_info_md(disp, md):
            for ref in ysp__safe_refs(md['references']):
                if ref['type'] != disp:
                    continue
                msg(" %s %-8s %s" % (str(ref['id']), md['type'], pkg))
        else:
            msg("%s %-8s %s" % (md['update_id'], md['type'], pkg))

    def show_pkg_exit(self):
        pass
            
    def doCommand(self, base, basecmd, extcmds):
        ygh = base.doPackageLists('updates')
        self.repos = base.repos
        md_info = ysp_gen_metadata(self)
        done = False
        logger = logging.getLogger("yum.verbose.main")
        def msg(x):
            logger.log(logginglevels.INFO_2, x)
        def msg_warn(x):
            logger.warn(x)

        opts, cmdline = base.plugins.cmdline
        ygh.updates.sort(key=lambda x: x.name)
        filt_type = None
        show_type = None
        if len(extcmds) >= 1:
            filt_type = extcmds.pop(0)
            
            if False:
                pass

            elif filt_type == "bugzillas":
                filt_type = "bugzilla"
            elif filt_type == "bzs":
                filt_type = "bugzilla"
            elif filt_type == "bz":
                filt_type = "bugzilla"
            elif filt_type == "bugzilla":
                pass
            
            elif filt_type == "sec":
                filt_type = "security"
            elif filt_type == "security":
                pass
            
            elif filt_type == "cves":
                filt_type = "cve"
            elif filt_type == "cve":
                pass
            else:
                extcmds = [filt_type] + extcmds
                filt_type = None
            show_type = filt_type
            if filt_type and filt_type == "security":
                show_type = None
            
        opts.sec_cmds = extcmds
        used_map = ysp_gen_used_map(opts)
        for pkg in ygh.updates:
            md = ysp_should_show_pkg(opts, pkg, md_info, used_map,
                                     filt_type)
            if not md:
                continue
            self.show_pkg(msg, pkg, md, show_type)
        ysp_chk_used_map(used_map, msg)

        self.show_pkg_exit()
        return 0, [basecmd + ' done']
            
class SecurityInfoCommands(SecurityListCommands):
    show_pkg_info_done = {}
    def getNames(self):
        return ['info-security', 'info-sec']

    def show_pkg(self, msg, pkg, md, disp=None):
        if md['update_id'] in self.show_pkg_info_done:
            return
        self.show_pkg_info_done[md['update_id']] = True
        msg(md)
    
    def show_pkg_exit(self):
        self.show_pkg_info_done = {}
            
def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Setup the option parser with the '--advisory', '--bz', '--cve', and
    '--security' command line options. And the 'sec-list' command.
    '''

    parser = conduit.getOptParser()
    if not parser:
        return

    conduit.registerCommand(SecurityListCommands())
    conduit.registerCommand(SecurityInfoCommands())
    parser.values.advisory = []
    parser.values.cve      = []
    parser.values.bz       = []
    parser.values.security = False
    def osec(opt, key, val, parser):
         # CVE is a subset of --security on RHEL, but not on Fedora
        if False and parser.values.cve:
            raise OptionValueError("can't use %s after --cve" % key)
        parser.values.security = True
    def ocve(opt, key, val, parser):
        if False and parser.values.security:
            raise OptionValueError("can't use %s after --security" % key)
        parser.values.cve.append(val)
    def obz(opt, key, val, parser):
        parser.values.bz.append(str(val))
    def oadv(opt, key, val, parser):
        parser.values.advisory.append(val)
            
    parser.add_option('--security', action="callback",
                      callback=osec, dest='security', default=False,
                      help='Include security relevant packages')
    parser.add_option('--cve', action="callback", type="string",
                      callback=ocve, dest='cve', default=[],
                      help='Include packages needed to fix the given CVE')
    parser.add_option('--bz', action="callback",
                      callback=obz, dest='bz', default=[], type="int",
                      help='Include packages needed to fix the given BZ')
    parser.add_option('--advisory', action="callback",
                      callback=oadv, dest='advisory', default=[], type="string",
                      help='Include packages needed to fix the given advisory')

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
def ysp_should_keep_pkg(opts, pkg, md, used_map):
    """ Do we want to keep this package to satisfy the security limits. """
    
    md = md.get_notice((pkg.name, pkg.ver, pkg.rel))
    if not md:
        return False
    
    return ysp_should_filter_pkg(opts, pkg, md, used_map)

def ysp_check_func_enter(conduit):
    """ Stuff we need to do in both list and update modes. """
    
    opts, args = conduit.getCmdLine()

    ndata = not (opts.security or opts.advisory or opts.bz or opts.cve)
    
    ret = None
    if len(args) >= 2:
        if ((args[0] == "list") and (args[1] == "updates")):
            ret = {"skip": ndata, "list_cmd": True}
        if ((args[0] == "info") and (args[1] == "updates")):
            ret = {"skip": ndata, "list_cmd": True}
    if len(args):
        if (args[0] == "check-update"):
            ret = {"skip": ndata, "list_cmd": True}
        if (args[0] == "update"):
            ret = {"skip": ndata, "list_cmd": False}
        if (args[0] == "list-sec") or (args[0] == "list-security"):
            return (opts, {"skip": True, "list_cmd": True})
        if (args[0] == "info-sec") or (args[0] == "info-security"):
            return (opts, {"skip": True, "list_cmd": True})

    if ret:
        if ndata:
            conduit.info(2, 'Skipping security plugin, no data')
        return (opts, ret)
    
    if not ndata:
        conduit.error(2, 'Skipping security plugin, other command')
    return (opts, {"skip": True, "list_cmd": False, "msg": True})

def exclude_hook(conduit):
    '''
    Yum Plugin Exclude Hook:
    Check and remove packages that don\'t align with the security config.
    '''
    
    opts, info = ysp_check_func_enter(conduit)
    if info["skip"]:
        return

    if not info["list_cmd"]:
        return
    
    conduit.info(2, 'Limiting package lists to security relevant ones')
    
    md_info = ysp_gen_metadata(conduit)

    def ysp_del_pkg(pkg):
        """ Deletes a package from all trees that yum knows about """
        conduit.info(3," --> %s from %s excluded (non-security)" %
                     (pkg,pkg.repoid))
        conduit.delPackage(pkg)

    opts.sec_cmds = []
    used_map = ysp_gen_used_map(opts)
    # The official API is:
    #
    # pkgs = conduit.getPackages()
    #
    # ...however that is _extremely_ slow, deleting all packages. So we ask
    # for the list of update packages, which is all we care about.
    upds = conduit._base.doPackageLists(pkgnarrow='updates')
    pkgs = upds.updates
    tot = 0
    cnt = 0
    for pkg in pkgs:
        tot += 1
        if ysp_should_keep_pkg(opts, pkg, md_info, used_map):
            cnt += 1
        else:
            ysp_del_pkg(pkg)
    ysp_chk_used_map(used_map, lambda x: conduit.error(2, x))
    if cnt:
        conduit.info(2, 'Needed %d of %d packages, for security' % (cnt, tot))
    else:
        conduit.info(2, 'No packages needed, for security, %d available' % tot)
            
def preresolve_hook(conduit):
    '''
    Yum Plugin PreResolve Hook:
    Check and remove packages that don\'t align with the security config.
    '''

    opts, info = ysp_check_func_enter(conduit)
    if info["skip"]:
        return

    if info["list_cmd"]:
        return
    
    conduit.info(2, 'Limiting packages to security relevant ones')

    md_info = ysp_gen_metadata(conduit)

    def ysp_del_pkg(tspkg):
        """ Deletes a package within a transaction. """
        conduit.info(3," --> %s from %s excluded (non-security)" %
                     (tspkg.po,tspkg.po.repoid))
        tsinfo.remove(tspkg.pkgtup)

    tot = 0
    cnt = 0
    opts.sec_cmds = []
    used_map = ysp_gen_used_map(opts)
    tsinfo = conduit.getTsInfo()
    tspkgs = tsinfo.getMembers()
    for tspkg in tspkgs:
        tot += 1
        if not ysp_should_keep_pkg(opts, tspkg.po, md_info, used_map):
            ysp_del_pkg(tspkg)
        else:
            cnt += 1
    ysp_chk_used_map(used_map, lambda x: conduit.error(2, x))
    
    if cnt:
        conduit.info(2, 'Needed %d of %d packages, for security' % (cnt, tot))
    else:
        conduit.info(2, 'No packages needed, for security, %d available' % tot)

if __name__ == '__main__':
    print "This is a plugin that is supposed to run from inside YUM"

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
#  yum --security info updates
#  yum --security list updates
#  yum --security check-update
#  yum --security update
#
# yum --cve CVE-2007-1667      <cmd>
# yum --bz  235374 --bz 234688 <cmd>
# yum --advisory FEDORA-2007-420 --advisory FEDORA-2007-346 <cmd>
#
# yum list-security
# yum list-security bugzillas / bzs
# yum list-security cves
# yum list-security security / sec
#
# yum update-minimal --security

import yum
import fnmatch
from yum.plugins import TYPE_INTERACTIVE
from yum.update_md import UpdateMetadata
import logging # for commands
from yum import logginglevels

from yum.constants import *

import rpmUtils.miscutils

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)
__package_name__ = "yum-plugin-security"

# newpackages is weird, in that we'll never display that because we filter to
# things relevant to installed pkgs...
__update_info_types__ = ("security", "bugfix", "enhancement",
                         "recommended", "newpackages")

def _rpm_tup_vercmp(tup1, tup2):
    """ Compare two "std." tuples, (n, a, e, v, r). """
    return rpmUtils.miscutils.compareEVR((tup1[2], tup1[3], tup1[4]),
                                         (tup2[2], tup2[3], tup2[4]))

class CliError(yum.Errors.YumBaseError):

    """
    Command line interface related Exception.
    """

    def __init__(self, args=''):
        yum.Errors.YumBaseError.__init__(self)
        self.args = args

def ysp_gen_metadata(repos):
    """ Generate the info. from the updateinfo.xml files. """
    md_info = UpdateMetadata()
    for repo in repos:
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

def _match_sec_cmd(sec_cmds, pkgname, notice):
    for i in sec_cmds:
        if fnmatch.fnmatch(pkgname, i):
            return i
        if notice['update_id'] == i:
            return i
    return None

def _has_id(used_map, refs, ref_type, ref_ids):
    ''' Check if the given ID is a match. '''
    for ref in ysp__safe_refs(refs):
        if ref['type'] != ref_type:
            continue
        if ref['id'] not in ref_ids:
            continue
        used_map[ref_type][ref['id']] = True
        return ref
    return None
    
def ysp_should_filter_pkg(opts, pkgname, notice, used_map):
    """ Do the package filtering for should_show and should_keep. """
    
    rcmd = _match_sec_cmd(opts.sec_cmds, pkgname, notice)
    if rcmd:
        used_map['cmd'][rcmd] = True
        return True
    elif opts.advisory and notice['update_id'] in opts.advisory:
        used_map['id'][notice['update_id']] = True
        return True
    elif opts.cve and _has_id(used_map, notice['references'], "cve", opts.cve):
        return True
    elif opts.bz and _has_id(used_map, notice['references'],"bugzilla",opts.bz):
        return True
    # FIXME: Add opts for enhancement/etc.? -- __update_info_types__
    elif opts.security and notice['type'] == 'security':
        return True
    elif opts.bugfixes and notice['type'] == 'bugfix':
        return True
    elif not (opts.advisory or opts.cve or opts.bz or
              opts.security or opts.bugfixes or opts.sec_cmds):
        return True # This is only possible from should_show_pkg
    return False

def ysp_has_info_md(rname, md):
    if rname in __update_info_types__:
        if md['type'] == rname:
            return md
    for ref in ysp__safe_refs(md['references']):
        if ref['type'] != rname:
            continue
        return md

def ysp_should_show_pkgtup(opts, pkgtup, md_info, used_map, rname=None):
    """ Do we want to show this package in list-security. """
    
    name = pkgtup[0]
    for (pkgtup, notice) in reversed(md_info.get_applicable_notices(pkgtup)):
        if rname and not ysp_has_info_md(rname, notice):
            continue
        if ysp_should_filter_pkg(opts, name, notice, used_map):
            yield (pkgtup, notice)

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

class SecurityListCommand:
    def getNames(self):
        return ['list-security', 'list-sec']

    def getUsage(self):
        return "[security|bugzilla|cve] [PACKAGE-wildcard]"

    def getSummary(self):
        return "Returns security data for the packages listed, that affects your system"

    def doCheck(self, base, basecmd, extcmds):
        pass

    def show_pkg(self, msg, pkg, notice, disp=None):
        # Make the list view much smaller
        # ysp_show_pkg_md_info(pkg, md, msg)
        if disp and ysp_has_info_md(disp, notice):
            for ref in ysp__safe_refs(notice['references']):
                if ref['type'] != disp:
                    continue
                msg(" %s %-8s %s" % (str(ref['id']), notice['type'], pkg))
        else:
            msg("%s %-8s %s" % (notice['update_id'], notice['type'], pkg))

    def show_pkg_exit(self):
        pass
            
    def doCommand(self, base, basecmd, extcmds):
        self.repos = base.repos
        md_info = ysp_gen_metadata(self.repos.listEnabled())
        logger = logging.getLogger("yum.verbose.main")
        def msg(x):
            logger.log(logginglevels.INFO_2, x)

        opts, cmdline = base.plugins.cmdline
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
            elif filt_type in __update_info_types__:
                pass
            
            elif filt_type == "cves":
                filt_type = "cve"
            elif filt_type == "cve":
                pass
            else:
                extcmds = [filt_type] + extcmds
                filt_type = None
            show_type = filt_type
            if filt_type and filt_type in __update_info_types__:
                show_type = None
            
        opts.sec_cmds = extcmds
        used_map = ysp_gen_used_map(opts)
        name2tup = _get_name2oldpkgtup(base)
        for pkgname in sorted(name2tup):
            for (pkgtup, notice) in ysp_should_show_pkgtup(opts,
                                                           name2tup[pkgname],
                                                           md_info,
                                                           used_map, filt_type):
                d = {}
                (d['n'], d['a'], d['e'], d['v'], d['r']) = pkgtup
                if d['e'] == '0':
                    d['epoch'] = ''
                else:
                    d['epoch'] = "%s:" % d['e']
                self.show_pkg(msg, "%(n)s-%(epoch)s%(v)s-%(r)s.%(a)s" % d,
                              notice, show_type)
        ysp_chk_used_map(used_map, msg)

        self.show_pkg_exit()
        return 0, [basecmd + ' done']
            
class SecurityInfoCommand(SecurityListCommand):
    show_pkg_info_done = {}
    def getNames(self):
        return ['info-security', 'info-sec']

    def show_pkg(self, msg, pkg, notice, disp=None):
        if notice['update_id'] in self.show_pkg_info_done:
            return
        self.show_pkg_info_done[notice['update_id']] = True
        # Python-2.4.* doesn't understand str(x) returning unicode *sigh*
        obj = notice.__str__()
        msg(obj)
    
    def show_pkg_exit(self):
        self.show_pkg_info_done = {}

# "Borrowed" from yumcommands.py
def yumcommands_checkRootUID(base):
    """
    Verify that the program is being run by the root user.

    @param base: a YumBase object.
    """
    if base.conf.uid != 0:
        base.logger.critical('You need to be root to perform this command.')
        raise CliError
def yumcommands_checkGPGKey(base):
    if not base.gpgKeyCheck():
        for repo in base.repos.listEnabled():
            if repo.gpgcheck != 'false' and repo.gpgkey == '':
                msg = """
You have enabled checking of packages via GPG keys. This is a good thing. 
However, you do not have any GPG public keys installed. You need to download
the keys for packages you wish to install and install them.
You can do that by running the command:
    rpm --import public.gpg.key


Alternatively you can specify the url to the key you would like to use
for a repository in the 'gpgkey' option in a repository section and yum 
will install it for you.

For more information contact your distribution or package provider.
"""
                base.logger.critical(msg)
                raise CliError

#  We need the list of installed pkgs, that are going to be updated
# (by default). Then we match their names to the above.
def _get_name2oldpkgtup(base):
    oupdates = map(lambda x: x[1], base.up.getUpdatesTuples())
    name2tup = {}
    for pkgtup in oupdates: # Get the latest "old" pkgtups
        if (pkgtup[0] in name2tup and
            _rpm_tup_vercmp(name2tup[pkgtup[0]], pkgtup) > 0):
            continue
        name2tup[pkgtup[0]] = pkgtup
    return name2tup

class SecurityUpdateCommand:
    def getNames(self):
        return ['update-minimal']

    def getUsage(self):
        return "[PACKAGE-wildcard]"

    def getSummary(self):
        return "Works like update, but goes to the 'newest' package match which fixes a problem that affects your system"

    def doCheck(self, base, basecmd, extcmds):
        yumcommands_checkRootUID(base)
        yumcommands_checkGPGKey(base)

    def doCommand(self, base, basecmd, extcmds):
        md_info       = ysp_gen_metadata(base.repos.listEnabled())
        opts          = base.plugins.cmdline[0]
        opts.sec_cmds = []
        used_map      = ysp_gen_used_map(opts)

        ndata = not (opts.security or opts.bugfixes or
                     opts.advisory or opts.bz or opts.cve)

        # NOTE: Not doing obsoletes processing atm. ... maybe we should? --
        # Also worth pointing out we don't go backwards for obsoletes in the:
        # update --security case etc.

        # obsoletes = base.up.getObsoletesTuples(newest=False)
        # for (obsoleting, installed) in sorted(obsoletes, key=lambda x: x[0]):
        #   pass

        # Tuples == (n, a, e, v, r)
        oupdates  = map(lambda x: x[1], base.up.getUpdatesTuples())
        for oldpkgtup in sorted(oupdates):
            data = md_info.get_applicable_notices(oldpkgtup)
            if ndata: # No options means pick the oldest update
                data.reverse()

            for (pkgtup, notice) in data:
                name = pkgtup[0]
                if extcmds and not _match_sec_cmd(extcmds, name, notice):
                    continue
                if (not ndata and
                    not ysp_should_filter_pkg(opts, name, notice, used_map)):
                    continue
                base.update(name=pkgtup[0], arch=pkgtup[1], epoch=pkgtup[2],
                            version=pkgtup[3], release=pkgtup[4])
                break

        if len(base.tsInfo) > 0:
            msg = '%d packages marked for minimal Update' % len(base.tsInfo)
            return 2, [msg]
        else:
            return 0, ['No Packages marked for minimal Update']

def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Setup the option parser with the '--advisory', '--bz', '--cve', and
    '--security' command line options. And the 'list-security',
    'info-security', and 'update-minimal' commands.
    '''

    parser = conduit.getOptParser()
    if not parser:
        return

    if hasattr(parser, 'plugin_option_group'):
        parser = parser.plugin_option_group

    conduit.registerCommand(SecurityListCommand())
    conduit.registerCommand(SecurityInfoCommand())
    conduit.registerCommand(SecurityUpdateCommand())
    def osec(opt, key, val, parser):
         # CVE is a subset of --security on RHEL, but not on Fedora
        parser.values.security = True
    def obug(opt, key, val, parser):
        parser.values.bugfixes = True
    def ocve(opt, key, val, parser):
        parser.values.cve.append(val)
    def obz(opt, key, val, parser):
        parser.values.bz.append(str(val))
    def oadv(opt, key, val, parser):
        parser.values.advisory.append(val)
            
    parser.add_option('--security', action="callback",
                      callback=osec, dest='security', default=False,
                      help='Include security relevant packages')
    parser.add_option('--bugfixes', action="callback",
                      callback=obug, dest='bugfixes', default=False,
                      help='Include bugfix relevant packages')
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
def ysp_should_keep_pkg(opts, pkgtup, md_info, used_map):
    """ Do we want to keep this package to satisfy the security limits. """
    name = pkgtup[0]
    for (pkgtup, notice) in md_info.get_applicable_notices(pkgtup):
        if ysp_should_filter_pkg(opts, name, notice, used_map):
            return True
    return False

def ysp_check_func_enter(conduit):
    """ Stuff we need to do in both list and update modes. """
    
    opts, args = conduit.getCmdLine()

    ndata = not (opts.security or opts.bugfixes or
                 opts.advisory or opts.bz or opts.cve)
    
    ret = None
    if len(args) >= 2:
        if ((args[0] == "list") and (args[1] in ("obsoletes", "updates"))):
            ret = {"skip": ndata, "list_cmd": True}
        if ((args[0] == "info") and (args[1] in ("obsoletes", "updates"))):
            ret = {"skip": ndata, "list_cmd": True}
    if len(args):

        # All the args. stuff is done in our command:
        if (args[0] == "update-minimal"):
            return (opts, {"skip": True, "list_cmd": False, "msg": True})
            
        if (args[0] == "check-update"):
            ret = {"skip": ndata, "list_cmd": True}
        if (args[0] in ["update", "upgrade"]):
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
    
    if hasattr(conduit, 'registerPackageName'):
        conduit.registerPackageName(__package_name__)
    conduit.info(2, 'Limiting package lists to security relevant ones')
    
    md_info = ysp_gen_metadata(conduit.getRepos().listEnabled())

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
    # In theory we don't need to do this in some cases, but meh.
    upds = conduit._base.doPackageLists(pkgnarrow='obsoletes')
    pkgs += upds.obsoletes

    name2tup = _get_name2oldpkgtup(conduit._base)
    
    tot = 0
    cnt = 0
    for pkg in pkgs:
        tot += 1
        name = pkg.name
        if (name not in name2tup or
            not ysp_should_keep_pkg(opts, name2tup[name], md_info, used_map)):
            ysp_del_pkg(pkg)
            continue
        cnt += 1

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
    
    if hasattr(conduit, 'registerPackageName'):
        conduit.registerPackageName(__package_name__)
    conduit.info(2, 'Limiting packages to security relevant ones')

    md_info = ysp_gen_metadata(conduit.getRepos().listEnabled())

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
    #  Ok, here we keep any pkgs that pass "ysp" tests, then we keep all
    # related pkgs ... Ie. "installed" version marked for removal.
    keep_pkgs = set()

    count_states = set(TS_INSTALL_STATES + [TS_ERASE])
    count_pkgs = set()
    for tspkg in tspkgs:
        if tspkg.output_state in count_states:
            count_pkgs.add(tspkg.po)

    name2tup = _get_name2oldpkgtup(conduit._base)
    for tspkg in tspkgs:
        if tspkg.output_state in count_states:
            tot += 1
        name = tspkg.po.name
        if (name not in name2tup or
            not ysp_should_keep_pkg(opts, name2tup[name], md_info, used_map)):
            continue
        if tspkg.output_state in count_states:
            cnt += 1
        keep_pkgs.add(tspkg.po)

    scnt = cnt
    mini_depsolve_again = True
    while mini_depsolve_again:
        mini_depsolve_again = False

        for tspkg in tspkgs:
            if tspkg.po in keep_pkgs:
                # Find any related pkgs, and add them:
                for (rpkg, reason) in tspkg.relatedto:
                    if rpkg not in keep_pkgs:
                        if rpkg in count_pkgs:
                            cnt += 1
                        keep_pkgs.add(rpkg)
                        mini_depsolve_again = True
            else:
                # If related to any keep pkgs, add us
                for (rpkg, reason) in tspkg.relatedto:
                    if rpkg in keep_pkgs:
                        if rpkg in count_pkgs:
                            cnt += 1
                        keep_pkgs.add(tspkg.po)
                        mini_depsolve_again = True
                        break

    for tspkg in tspkgs:
        if tspkg.po not in keep_pkgs:
            ysp_del_pkg(tspkg)

    ysp_chk_used_map(used_map, lambda x: conduit.error(2, x))
    
    if cnt:
        conduit.info(2, 'Needed %d (+%d related) of %d packages (so far), for security' % (scnt, cnt - scnt, tot))
    else:
        conduit.info(2, 'No packages needed, for security, of %d packages (so far)' % tot)

if __name__ == '__main__':
    print "This is a plugin that is supposed to run from inside YUM"

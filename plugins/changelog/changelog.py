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
#    James Antill    <james@and.org>
#
# TODO: 
# - In 'pre' mode we could get the changelogs from rpmdb thus avoiding
#   the costly 'otherdata' import.

import time
from rpmUtils.miscutils import splitFilename
from yum.plugins import TYPE_INTERACTIVE
from yum.plugins import PluginYumExit

from yum import logginglevels
import logging

from yum.i18n import to_unicode

from yum.update_md import UpdateMetadata

try:
    import dateutil.parser as dateutil_parser
except ImportError:
    dateutil_parser = None
requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)

origpkgs = {}
changelog = False
orignots = set()
also_updateinfo = False
updateinfo = False

def changelog_delta(pkg, olddate):
    out = []
    for date, author, message in pkg.returnChangelog():
        if int(date) > olddate:
            out.append("* %s %s\n%s" % (time.ctime(int(date)), author, message))
    return out

def srpmname(pkg):
    n,v,r,e,a = splitFilename(pkg.returnSimple('sourcerpm'))
    return n

def _show_changes_changelog(conduit, srpms):
    for name in sorted(srpms.keys()):
        rpms = []
        if origpkgs.has_key(name):
            for rpm in srpms[name]:
                rpms.append("%s" % rpm)
            done = False
            kvf = conduit._base.fmtKeyValFill
            rpm_names = ", ".join(sorted(rpms))
            for line in changelog_delta(srpms[name][0], origpkgs[name]):
                if not done:
                    conduit.info(2,kvf("ChangeLog for: ", rpm_names))
                done = True
                conduit.info(2, "%s\n" % to_unicode(line))
            if not done:
                conduit.info(2, "%s\n" % kvf("** No ChangeLog for: ",rpm_names))

def _show_changes_updateinfo(conduit):
    for note in sorted(orignots):
        conduit.info(2, note)

def show_changes(conduit, msg):
    # Group by src.rpm name, not binary to avoid showing duplicate changelogs
    # for subpackages
    srpms = {}
    ts = conduit.getTsInfo()
    for tsmem in ts.getMembers():
        if not tsmem.updates:
            continue
        name = srpmname(tsmem.po)
        if srpms.has_key(name):
            srpms[name].append(tsmem.po)
        else:
            srpms[name] = [tsmem.po]

    conduit.info(2, "\n%s\n" % msg)
    if changelog:
        _show_changes_changelog(conduit, srpms)
    if updateinfo:
        _show_changes_updateinfo(conduit)

class ChangeLogCommand:

    def getNames(self):
        return ['changelog', 'ChangeLog']

    def getUsage(self):
        return "<date>|<number>|all [PACKAGE|all|installed|updates|extras|obsoletes|recent]"

    def getSummary(self):
        return """\
Display changelog data, since a specified time, on a group of packages"""

    def doCheck(self, base, basecmd, extcmds):
        pass

    def changelog(self, pkg):
        if self._since_all:
            for date, author, message in pkg.returnChangelog():
                yield "* %s %s\n%s" % (time.ctime(int(date)), author, message)
            return

        if self._since_num is not None:
            num = self._since_num
            for date, author, message in pkg.returnChangelog():
                if num <= 0:
                    return
                num -= 1
                yield "* %s %s\n%s" % (time.ctime(int(date)), author, message)
            return
        
        if True:
            for date, author, message in pkg.returnChangelog():
                if int(date) < self._since_tt:
                    return
                yield "* %s %s\n%s" % (time.ctime(int(date)), author, message)

    def show_data(self, msg, pkgs, name):
        done = False
        for pkg in pkgs:
            self._pkgs += 1
            if pkg.sourcerpm in self._done_spkgs:
                continue

            self._spkgs += 1

            for line in self.changelog(pkg):
                if pkg.sourcerpm not in self._done_spkgs:                    
                    if not self._done_spkgs:
                        msg('')
                        if self._since_all:
                            msg('Listing all changelogs')
                        elif self._since_num is not None:
                            sn = "s"
                            if self._since_num == 1:
                                sn = ""
                            msg('Listing %d changelog%s' % (self._since_num,sn))
                        else:
                            msg('Listing changelogs since ' +
                                str(self._since_dto.date()))
                    msg('')
                    if not done:
                        msg("%s %s %s" % ('=' * 20, name, '=' * 20))
                    done = True

                    self._done_spkgs[pkg.sourcerpm] = True
                    msg('%-40.40s %s' % (pkg, pkg.repoid))
                self._changelogs += 1
                msg(line)
                msg('')

    def doCommand(self, base, basecmd, extcmds):
        logger = logging.getLogger("yum.verbose.main")
        def msg(x):
            logger.log(logginglevels.INFO_2, x)
        def msg_warn(x):
            logger.warn(x)

        self._done_spkgs = {}
        self._pkgs = 0
        self._spkgs = 0
        self._changelogs = 0
        self._since_all = False
        self._since_dto = None
        self._since_tt  = None
        self._since_num = None

        if not len(extcmds):
            return 1, [basecmd + " " + self.getUsage()]
        
        since = extcmds[0]
        extcmds = extcmds[1:]

        if since == 'all':
            self._since_all = True
        else:
            try:
                num = int(since)
                if num <= 0:
                    raise ValueError
                self._since_num = num
            except:
                if dateutil_parser is None:
                    msg = "Dateutil module not available, so can't parse dates"
                    raise PluginYumExit(msg)
                try:
                    self._since_dto = dateutil_parser.parse(since, fuzzy=True)
                except ValueError:
                    msg = "Argument -- %s -- is not \"all\", a positive number or a date" % since
                    raise PluginYumExit(msg)
                tt = self._since_dto.timetuple()
                self._since_tt = time.mktime(tt)

        ypl = base.returnPkgLists(extcmds)
        self.show_data(msg, ypl.installed, 'Installed Packages')
        self.show_data(msg, ypl.available, 'Available Packages')
        self.show_data(msg, ypl.extras,    'Extra Packages')
        self.show_data(msg, ypl.updates,   'Updated Packages')
        self.show_data(msg, ypl.obsoletes, 'Obsoleting Packages')
        self.show_data(msg, ypl.recent,    'Recent Packages')

        ps = sps = cs = ""
        if self._pkgs       != 1: ps  = "s"
        if self._spkgs      != 1: sps = "s"
        if self._changelogs != 1: cs  = "s"
        return 0, [basecmd +
                   ' stats. %d pkg%s, %d source pkg%s, %d changelog%s' %
                   (self._pkgs, ps, self._spkgs, sps, self._changelogs, cs)]

    def needTs(self, base, basecmd, extcmds):
        if len(extcmds) and extcmds[0] == 'installed':
            return False
        
        return True

def config_hook(conduit):
    conduit.registerCommand(ChangeLogCommand())
    parser = conduit.getOptParser()
    if parser:
        if conduit.confBool('main', 'always', default=False):
            global changelog
            changelog = True
        if conduit.confBool('main', 'updateinfo', default=True):
            global also_updateinfo
            also_updateinfo = True
        if (also_updateinfo and
            conduit.confBool('main', 'updateinfo_always', default=changelog)):
            global updateinfo
            updateinfo = True
        if changelog and (not also_updateinfo or updateinfo):
            return
        if hasattr(parser, 'plugin_option_group'):
            parser = parser.plugin_option_group
        parser.add_option('--changelog', action='store_true', 
                      help='Show changelog delta of updated packages')

def _setup_changelog_from_cmdline(conduit):
    global changelog
    global updateinfo
    opts, args = conduit.getCmdLine()
    if opts:
        if not changelog:
            changelog = opts.changelog
        if not updateinfo:
            updateinfo = opts.changelog

def postresolve_hook(conduit):
    _setup_changelog_from_cmdline(conduit)

    if not (changelog or updateinfo) or conduit.resultcode == 1:
        return

    # Find currently installed versions of packages we're about to update
    ts = conduit.getTsInfo()
    rpmdb = conduit.getRpmDB()
    if updateinfo:
        repos = set()
        for tsmem in ts.getMembers():
            if tsmem.po.repoid == 'installed':
                continue
            repos.add(tsmem.po.repo)
        mdi = UpdateMetadata(repos=list(repos))
    for tsmem in ts.getMembers():
        for po in rpmdb.searchNevra(name=tsmem.po.name, arch=tsmem.po.arch):
            hdr = po.hdr
            times = hdr['changelogtime']
            n,v,r,e,a = splitFilename(hdr['sourcerpm'])
            if len(times) == 0:
                # deal with packages without changelog
                origpkgs[n] = 0 
            else:
                origpkgs[n] = times[0]
            if updateinfo:
                for (pkgtup, notice) in mdi.get_applicable_notices(po.pkgtup):
                    orignots.add(notice)

    if conduit.confString('main', 'when', default='post') == 'pre':
        show_changes(conduit, 'Changes in packages about to be updated:')

def posttrans_hook(conduit):
    if not (changelog or updateinfo): 
        return

    if conduit.confString('main', 'when', default='post') == "post":
        show_changes(conduit, 'Changes in updated packages:')



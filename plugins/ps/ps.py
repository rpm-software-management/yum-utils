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
# Copyright Red Hat Inc. 2010
#
# Author: James Antill <james.antill@redhat.com>
#
# Examples:
#
#  yum ps k\*
#  yum ps all

import yum
import yum.misc as misc
from yum.plugins import TYPE_INTERACTIVE

from urlgrabber.progress import format_number
try:
    import utils
except ImportError:
    #  This only happens when we are imported but aren't going to be run
    # due to being type ITERACTIVE.
    utils = None

import fnmatch
import time

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)

def _rpmdb_return_running_packages(self, return_pids=False):
        """returns a list of yum installed package objects which own a file
           that are currently running or in use."""
        pkgs = {}
        for pid in misc.return_running_pids():
            for fn in misc.get_open_files(pid):
                for pkg in self.searchFiles(fn):
                    if pkg not in pkgs:
                        pkgs[pkg] = set()
                    pkgs[pkg].add(pid)

        if return_pids:
            return pkgs
        return sorted(pkgs.keys())


class PSCommand:
    def getNames(self):
        return ['ps']

    def getUsage(self):
        return "[all|updates|restart] [pkgs...]"

    def getSummary(self):
        return "List processes, which are packages"

    def doCheck(self, base, basecmd, extcmds):
        pass

    def doCommand(self, base, basecmd, extcmds):
        show_all = False
        show_upgrades = False
        if extcmds and extcmds[0] == 'all':
            show_all = True
            extcmds = extcmds[1:]
        elif extcmds and extcmds[0] in ('updates', 'upgrades'):
            show_upgrades = True
            extcmds = extcmds[1:]
        elif extcmds and extcmds[0] == 'restarts':
            extcmds = extcmds[1:]

        # Call base.rpmdb.return_running_packages() eventually.
        pkgs = _rpmdb_return_running_packages(base.rpmdb, return_pids=True)
        ts = base.rpmdb.readOnlyTS()
        kern_pkgtup = misc.get_running_kernel_pkgtup(ts)
        kern_pkg = None
        for pkg in sorted(base.rpmdb.searchPkgTuple(kern_pkgtup)):
            kern_pkg = pkg
        if kern_pkg is not None:
            kern_pkgs = base.rpmdb.searchNames([kern_pkgtup[0]])
            if kern_pkgs:
                kern_latest = sorted(kern_pkgs)[-1]
                if kern_latest.verGT(kern_pkg):
                    pkgs[kern_latest] = [0]

        try:
            # Get boot time, this is what get_process_info() uses:
            for line in open("/proc/stat"):
                if line.startswith("btime "):
                    kern_boot = int(line[len("btime "):-1])
                    break
        except:
            kern_boot = 0

        print "  %8s %-16s %8s %8s %10s %s" % ("pid", "proc",
                                               "CPU", "RSS", "State", "uptime")
        for pkg in sorted(pkgs):
            if extcmds:
                for cmd in extcmds:
                    if fnmatch.fnmatch(pkg.name, cmd):
                        break
                    if fnmatch.fnmatch(pkg.ui_nevra, cmd):
                        break
                else:
                    continue

            apkgs = base.pkgSack.searchNames([pkg.name])
            state = ''
            if not apkgs:
                apkgs = 'Not available!'
            else:
                apkgs = sorted(apkgs)[-1]
                if apkgs.verEQ(pkg):
                    apkgs = ''
                    state = ''
                elif apkgs.verGT(pkg):
                    state = 'Upgrade'
                    apkgs = apkgs.ui_nevra[len(apkgs.name)+1:]
                else:
                    state = 'Newer'
                    apkgs = apkgs.ui_nevra[len(apkgs.name)+1:]
            procs = []
            for pid in pkgs[pkg]:
                pid = int(pid)
                now = int(time.time())
                if pid:
                    ps_info = utils.get_process_info(pid)
                    if ps_info is None:
                        ps_info = {'name' : '<Unknown>',
                                   'start_time' : 0,
                                   'state' : 'Unknown',
                                   'vmrss' : 0, 'utime' : 0, 'stime' : 0}
                else:
                    ps_info = {'name' : '<kernel>',
                               'start_time' : kern_boot,
                               'state' : 'Running',
                               'vmrss' : 0, 'utime' : 0, 'stime' : 0}
                procs.append((ps_info['start_time'], pid, ps_info))
            oldest_proc = min([t[0] for t in procs])
            if show_all:
                pass
            elif oldest_proc < pkg.installtime:
                pass
            elif show_upgrades and state == 'Upgrade':
                pass
            else:
                continue
            print "%s %s %s" % (pkg, state, apkgs)
            for start_time, pid, ps_info in sorted(procs):
                ago = utils.seconds_to_ui_time(now - start_time)
                nr = ' '
                if start_time <= pkg.installtime:
                    nr = '*'
                name = ps_info['name']
                cpu  = int(ps_info['utime']) + int(ps_info['stime'])
                cpu  = "%d:%02d" % (cpu / 60, cpu % 60)
                rss  = format_number(int(ps_info['vmrss']) * 1024)
                S    = ps_info['state']
                print "  %8d %-16.16s %8s %7sB %10s: %s%s" % (pid, name,
                                                            cpu, rss, S,nr, ago)

        rc = 0
        return rc, ['%s' % basecmd]

    def needTs(self, base, basecmd, extcmds):
        return False


def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    And the 'ps' command.
    '''
    conduit.registerCommand(PSCommand())

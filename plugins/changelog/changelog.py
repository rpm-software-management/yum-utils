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
#
# TODO: 
# - In 'pre' mode we could get the changelogs from rpmdb thus avoiding
#   the costly 'otherdata' import.

import time
from rpmUtils.miscutils import splitFilename
from yum.plugins import TYPE_INTERACTIVE

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)

origpkgs = {}
changelog = 0

def changelog_delta(pkg, olddate):
    out = []
    for date, author, message in pkg.returnChangelog():
        if int(date) > olddate:
            out.append("* %s %s\n%s\n" % (time.ctime(int(date)), author, message))
    return out

def srpmname(pkg):
    n,v,r,e,a = splitFilename(pkg.returnSimple('sourcerpm'))
    return n

def show_changes(conduit, msg):
    # Group by src.rpm name, not binary to avoid showing duplicate changelogs
    # for subpackages
    srpms = {}
    ts = conduit.getTsInfo()
    for tsmem in ts.getMembers():
        name = srpmname(tsmem.po)
        if srpms.has_key(name):
            srpms[name].append(tsmem.po)
        else:
            srpms[name] = [tsmem.po]

    conduit.info(2, "\n%s\n" % msg)
    for name in srpms.keys():
        rpms = []
        if origpkgs.has_key(name):
            for rpm in srpms[name]:
                rpms.append("%s" % rpm)
            conduit.info(2, ", ".join(rpms))
            for line in changelog_delta(srpms[name][0], origpkgs[name]):
                conduit.info(2, "%s\n" % line)

def config_hook(conduit):
    parser = conduit.getOptParser()
    if parser:
        parser.add_option('--changelog', action='store_true', 
                      help='Show changelog delta of updated packages')

def postreposetup_hook(conduit):
    global changelog
    opts, args = conduit.getCmdLine()
    if opts:
        changelog = opts.changelog

    if changelog:
        repos = conduit.getRepos()
        repos.populateSack(with='otherdata')

def postresolve_hook(conduit):
    if not changelog: 
        return

    # Find currently installed versions of packages we're about to update
    ts = conduit.getTsInfo()
    rpmdb = conduit.getRpmDB()
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

    if conduit.confString('main', 'when', default='post') == 'pre':
        show_changes(conduit, 'Changes in packages about to be updated:')

def posttrans_hook(conduit):
    if not changelog: 
        return

    if conduit.confString('main', 'when', default='post') == "post":
        show_changes(conduit, 'Changes in updated packages:')



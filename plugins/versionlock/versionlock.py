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
# tweaks by James Antill <james@and.org>
#

from yum.plugins import PluginYumExit
from yum.plugins import TYPE_CORE
from rpmUtils.miscutils import splitFilename, compareEVR
import urlgrabber
import urlgrabber.grabber

import os
import fnmatch
import tempfile

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)

_version_lock_excluder_n      = set()
_version_lock_excluder_nevr   = set()

#  In theory we could do full nevra/pkgtup ... but having foo-1.i386 and not
# foo-1.x86_64 would be pretty weird. So just do "archless".
# _version_lock_excluder_pkgtup = set()

fileurl = None

def _read_locklist():
    locklist = []
    try:
        llfile = urlgrabber.urlopen(fileurl)
        for line in llfile.readlines():
            if line.startswith('#') or line.strip() == '':
                continue
            locklist.append(line.rstrip())
        llfile.close()
    except urlgrabber.grabber.URLGrabError, e:
        raise PluginYumExit('Unable to read version lock configuration: %s' % e)
    return locklist

class VersionLockCommand:
    created = 1247693044

    def getNames(self):
        return ["versionlock"]

    def getUsage(self):
        return '[PACKAGE-wildcard]'

    def getSummary(self):
        return 'Control package version locks.'

    def doCheck(self, base, basecmd, extcmds):
        pass

    def doCommand(self, base, basecmd, extcmds):
        cmd = 'list'
        if extcmds:
            if extcmds[0] not in ('add', 'list', 'del', 'delete', 'clear'):
                cmd = 'add'
            else:
                cmd = {'del' : 'delete'}.get(extcmds[0], extcmds[0])
                extcmds = extcmds[1:]

        filename = fileurl
        if fileurl.startswith("file:"):
            filename = fileurl[len("file:"):]

        if not filename.startswith('/') and cmd != 'list':
            print "Error: versionlock URL isn't local: " + fileurl
            return 1, ["versionlock %s failed" % (cmd,)]

        if cmd == 'add':
            pkgs = base.rpmdb.returnPackages(patterns=extcmds)
            if not pkgs:
                pkgs = base.pkgSack.returnPackages(patterns=extcmds)

            fo = open(filename, 'a')
            count = 0
            done = set()
            for pkg in pkgs:
                #  We ignore arch, so only add one entry for foo-1.i386 and
                # foo-1.x86_64.
                (n, a, e, v, r) = pkg.pkgtup
                a = '*'
                if (n, a, e, v, r) in done:
                    continue
                done.add((n, a, e, v, r))

                print "Adding versionlock on: %s:%s-%s-%s" % (e, n, v, r)
                count += 1
                (n, a, e, v, r) = pkg.pkgtup
                fo.write("%s:%s-%s-%s.%s\n" % (e, n, v, r, '*'))

            return 0, ['versionlock added: ' + str(count)]

        if cmd == 'clear':
            open(filename, 'w')
            return 0, ['versionlock cleared']

        if cmd == 'delete':
            dirname = os.path.dirname(filename)
            (out, tmpfilename) = tempfile.mkstemp(dir=dirname, suffix='.tmp')
            out = os.fdopen(out, 'w', -1)
            count = 0
            for ent in _read_locklist():
                found = False
                for match in extcmds:
                    if fnmatch.fnmatch(ent, match):
                        found = True
                        break
                if found:
                    print "Deleting versionlock for:", ent
                    count += 1
                    continue
                out.write(ent)
                out.write('\n')
            out.close()
            if not count:
                os.unlink(tmpfilename)
                return 1, ['Error: versionlock delete: no matches']
            os.rename(tmpfilename, filename)
            return 0, ['versionlock deleted: ' + str(count)]

        assert cmd == 'list'
        for ent in _read_locklist():
            print ent

        return 0, ['versionlock list done']

    def needTs(self, base, basecmd, extcmds):
        return False

def config_hook(conduit):
    global fileurl

    fileurl = conduit.confString('main', 'locklist')

    if hasattr(conduit._base, 'registerCommand'):
        conduit.registerCommand(VersionLockCommand())

def exclude_hook(conduit):
    conduit.info(3, 'Reading version lock configuration')

    if not fileurl:
        raise PluginYumExit('Locklist not set')

    pkgs = {}
    for ent in _read_locklist():
        (n, v, r, e, a) = splitFilename(ent)
        n = n.lower()
        v = v.lower()
        r = r.lower()
        e = e.lower()
        if e == '': 
            e = '0'
        _version_lock_excluder_n.add(n)
        _version_lock_excluder_nevr.add("%s-%s:%s-%s" % (n, e, v, r))

    if conduit.confBool('main', 'follow_obsoletes', default=False):
        #  If anything obsoletes something that we have versionlocked ... then
        # remove all traces of that too.
        for (pkgtup, instTup) in conduit._base.up.getObsoletesTuples():
            if instTup[0] not in _version_lock_excluder_n:
                continue
            _version_lock_excluder_n.add(pkgtup[0].lower())

    if not _version_lock_excluder_n:
        return

    if hasattr(conduit, 'registerPackageName'):
        conduit.registerPackageName("yum-plugin-versionlock")
    ape = conduit._base.pkgSack.addPackageExcluder
    exid = 'yum-utils.versionlock.'
    ape(None, exid + str(1), 'wash.marked')
    ape(None, exid + str(2), 'mark.name.in', _version_lock_excluder_n)
    ape(None, exid + str(3), 'wash.nevr.in', _version_lock_excluder_nevr)
    ape(None, exid + str(4), 'exclude.marked')

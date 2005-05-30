#!/usr/bin/python -tt

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

import sys

sys.path.insert(0, '/usr/share/yum-cli')
import cli
import yum
import rpmUtils
import repomd.mdErrors
from yum.logger import Logger

def main(args):
    base = cli.YumBaseCli()
    base.doConfigSetup()
    base.log = Logger(threshold=base.conf.getConfigOption('debuglevel'), file_object =sys.stdout)

    archlist = rpmUtils.arch.getArchList() + ['src']
    base.doRepoSetup(dosack=0)
    base.doTsSetup()
    base.doRpmDBSetup()
    ts = rpmUtils.transaction.initReadOnlyTransaction()
    
    base.doSackSetup(archlist)

    for arg in args:
        if arg.endswith(".src.rpm"):
            srpm = yum.packages.YumLocalPackage(ts, arg)
        else:
            try:
                srpm = base.pkgSack.returnNewestByNameArch((arg, 'src'))
            except repomd.mdErrors.PackageSackError, e:
                base.errorlog(0, "Error: %s" % e)
                sys.exit(1)

        for dep in srpm.requiresList():
            if dep.startswith("rpmlib("): continue
            try:
                pkg = base.returnPackageByDep(dep)
                if not base.rpmdb.installed(name=pkg.name):
                    base.tsInfo.addInstall(pkg)
            except repomd.mdErrors.PackageSackError, e:
                base.errorlog(0, "Error: %s" % e)
                sys.exit(1)
                    
    (result, resultmsgs) = base.buildTransaction()
    if len(base.tsInfo) == 0:
        base.log(0, "Nothing to do")
    else: 
        base.listTransaction()
        base.doTransaction()



if __name__ == "__main__":
    main(sys.argv[1:])
                
# vim:sw=4:sts=4:expandtab              

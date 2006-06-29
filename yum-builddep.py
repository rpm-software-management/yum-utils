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

import sys, os

sys.path.insert(0, '/usr/share/yum-cli')
import cli
import yum
import rpmUtils
import yum.Errors
from yum.logger import Logger
from optparse import OptionParser

def parseArgs():
    usage = "usage: %s [options] package1 [package2] [package..]" % sys.argv[0]
    parser = OptionParser(usage=usage)
    parser.add_option("--repoid", default=[], dest="repos", action="append", 
      help='operate on a specific repo, can be specified multiple times', 
      metavar='[repo]')
    (opts, args) = parser.parse_args()
    if len(args) < 1: 
        parser.print_help()
        sys.exit(0)
    return (opts, args)

def main():
    opts, args = parseArgs()
    base = cli.YumBaseCli()
    base.doConfigSetup()
    base.conf.uid = os.geteuid()
        
    base.log = Logger(threshold=base.conf.debuglevel, file_object =sys.stdout)

    if base.conf.uid != 0:
        base.errorlog(0, "You must be root to install packages")
        sys.exit(1)

    if len(opts.repos) > 0:
        for repo in base.repos.findRepos('*'):
            if repo.id not in opts.repos:
                repo.disable()
            else:
                repo.enable()

    archlist = rpmUtils.arch.getArchList() + ['src']
    base.doRepoSetup(dosack=0)
    base.doTsSetup()
    base.doRpmDBSetup()
    ts = rpmUtils.transaction.initReadOnlyTransaction()
    
    base.doSackSetup(archlist)

    for arg in args:
        if arg.endswith(".src.rpm"):
            srpms = [yum.packages.YumLocalPackage(ts, arg)]
        else:
            try:
                srpms = base.pkgSack.returnNewestByNameArch((arg, 'src'))
            except yum.Errors.PackageSackError, e:
                base.errorlog(0, "Error: %s" % e)
                sys.exit(1)

        for srpm in srpms:
            for dep in srpm.requiresList():
                if dep.startswith("rpmlib("): continue
                try:
                    pkg = base.returnPackageByDep(dep)
                    if not base.rpmdb.installed(name=pkg.name):
                        base.tsInfo.addInstall(pkg)
                except yum.Errors.PackageSackError, e:
                    base.errorlog(0, "Error: %s" % e)
                    sys.exit(1)
                    
    (result, resultmsgs) = base.buildTransaction()
    if len(base.tsInfo) == 0:
        base.log(0, "Nothing to do")
    else: 
        base.listTransaction()
        base.doTransaction()



if __name__ == "__main__":
    main()
                
# vim:sw=4:sts=4:expandtab              

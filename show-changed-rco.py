#! /usr/bin/python -tt

#!/usr/bin/python -tt

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import yum

import os

from optparse import OptionParser
from optparse import SUPPRESS_HELP

version = "1.0.0"


def _get_npkgs(self, args):
    pkgs = []
    for arg in args:
        if (arg.endswith('.rpm') and (yum.misc.re_remote_url(arg) or
                                      os.path.exists(arg))):
            thispkg = yum.packages.YumUrlPackage(self, self.ts, arg)
            pkgs.append(thispkg)
        elif self.conf.showdupesfromrepos:
            pkgs.extend(self.pkgSack.returnPackages(patterns=[arg]))
        else:                
            try:
                pkgs.extend(self.pkgSack.returnNewestByName(patterns=[arg]))
            except yum.Errors.PackageSackError:
                pass
    return pkgs

def _get_opkgs(self, npkgs, old_packages):
    if old_packages:
        return _get_npkgs(self, old_packages)
    pkg_names = set((pkg.name for pkg in npkgs))
    return self.rpmdb.searchNames(pkg_names)

def _get_oreqs(pkg, reqs):
    oreqs = {}
    for req in reqs:
        (r,f,v) = req
        if r.startswith('rpmlib('):
            continue

        if r not in oreqs:
            oreqs[r] = set([req])
        else:
            oreqs[r].add(req)
    return oreqs

def _get_reqs(pkg, reqs, oreqs, self_prov_check=True):
    nreqs = set()
    creqs = set()

    for req in reqs:
        (r,f,v) = req
        if r.startswith('rpmlib('):
            continue

        if r in oreqs and req in oreqs[r]:
            continue

        if (r in pkg.provides_names or
            (r[0] == '/' and r in (pkg.filelist + pkg.dirlist +
                                   pkg.ghostlist))):
            if not f or pkg.checkPrco('provides', req):
                continue

        if r in oreqs:
            creqs.add(req)
        else:
            nreqs.add(req)

    return nreqs, creqs


def _print_reqs(yb, pkg, reqs, used_repos):
    out_reqs = {}
    for req in reqs:
        (r,f,v) = req
        seen = {}
        out_reqs[req] = []
        for pkg in sorted(yb.rpmdb.searchProvides(req)):
            key = (pkg.name, pkg.arch)
            if key in seen and not yb.conf.showdupesfromrepos:
                continue
            seen[key] = pkg
            out_reqs[req].append(pkg)
            used_repos.append(pkg.ui_from_repo)
        for pkg in sorted(yb.pkgSack.searchProvides(req)):
            key = (pkg.name, pkg.arch)
            if key in seen and not yb.conf.showdupesfromrepos:
                continue
            seen[key] = pkg
            out_reqs[req].append(pkg)
            used_repos.append(pkg.ui_from_repo)
    done = set()
    for req in sorted(out_reqs):
        if req in done:
            continue
        done.add(req)
        print " ", yum.misc.prco_tuple_to_string(req)
        for oreq in sorted(out_reqs):
            if oreq in done:
                continue
            if req == oreq:
                continue
            if out_reqs[oreq] == out_reqs[req]:
                print " ", yum.misc.prco_tuple_to_string(oreq)
                done.add(oreq)
        for pkg in out_reqs[req]:
            print "   ", pkg, pkg.ui_from_repo

def _print_sum(title, used_repos, ind=" ", end=' '):
    if not used_repos:
        return

    print title
    crepos = {}
    installed = 0
    available = 0
    for urepo in used_repos:
        if urepo not in crepos:
            crepos[urepo] = 0
        crepos[urepo] += 1
        if urepo[0] == '@':
            installed += 1
        else:
            available += 1

    if installed:
        print ind, "Installed:", installed
    for urepo in sorted(crepos):
        if urepo[0] != '@':
            continue
        print "%s%s" % (ind, "   "), urepo + ":", crepos[urepo]
    if available:
        print ind, "Available:", available
    for urepo in sorted(crepos):
        if urepo[0] == '@':
            continue
        print "%s%s" % (ind, "   "), urepo + ":", crepos[urepo]

    if end:
        print end


def main():
    parser = OptionParser(version = "Depcheck version %s" % version)
    parser.add_option("--releasever", default=None,
                      help="set value of $releasever in yum config and repo files")
    parser.add_option("--show-duplicates", action="store_true",
                      dest="show_dupes",
                      help="show all versions of packages")
    parser.add_option("--show-dupes", action="store_true",
                      help=SUPPRESS_HELP)
    parser.add_option("--repoid", action="append",
                      help="specify repoids to query, can be specified multiple times (default is all enabled)")
    parser.add_option("--enablerepo", action="append", dest="enablerepos",
                      help="specify additional repoids to query, can be specified multiple times")
    parser.add_option("--disablerepo", action="append", dest="disablerepos",
                      help="specify repoids to disable, can be specified multiple times")                      
    parser.add_option("--repofrompath", action="append",
                      help="specify repoid & paths of additional repositories - unique repoid and complete path required, can be specified multiple times. Example. --repofrompath=myrepo,/path/to/repo")
    parser.add_option("--old-packages", action="append",
                      help="packages to use to compare against, instead of installed")
    parser.add_option("--ignore-arch", action="store_true",
                      help="ignore arch when searching for old packages")
    parser.add_option("--skip-new", action="store_true",
                      help="skip packages without a matching old package")
    parser.add_option("-C", "--cache", action="store_true",
                      help="run from cache only")
    parser.add_option("-c", "--config", dest="conffile", default=None,
                      help="config file location")

    (opts, args) = parser.parse_args()


    yb = yum.YumBase()
    yb.preconf.releasever = opts.releasever
    if opts.conffile is not None:
        yb.preconf.fn = opts.conffile

    # setup the fake repos
    for repo in opts.repofrompath or []:
        tmp = tuple(repo.split(','))
        if len(tmp) != 2:
            yb.logger.error("Error: Bad repofrompath argument: %s" %repo)
            continue
        repoid,repopath = tmp
        if repopath[0] == '/':
            baseurl = 'file://' + repopath
        else:
            baseurl = repopath
        yb.add_enable_repo(repoid, baseurls=[baseurl],
                           basecachedir=yb.conf.cachedir)
        yb.logger.info("Added %s repo from %s" % (repoid, repopath))

    if opts.cache:
        yb.conf.cache = 1
    elif not yb.setCacheDir():
        yb.conf.cache = 1

    if opts.show_dupes:
        yb.conf.showdupesfromrepos = True

    if opts.repoid:
        found_repos = set()
        for repo in yb.repos.findRepos('*'):
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                found_repos.add(repo.id)
                repo.enable()
        for not_found in set(opts.repoid).difference(found_repos):
            yb.logger.error('Repoid %s was not found.' % not_found)

    if opts.disablerepos:
        for repo_match in opts.disablerepos:
            for repo in yb.repos.findRepos(repo_match):
                repo.disable()

    if opts.enablerepos:    
        for repo_match in opts.enablerepos:
            for repo in yb.repos.findRepos(repo_match):
                repo.enable()

    npkgs = _get_npkgs(yb, args)
    opkgs = {}
    for pkg in sorted(_get_opkgs(yb, npkgs, opts.old_packages)):
        opkgs[(pkg.name, pkg.arch)] = pkg
        opkgs[pkg.name] = pkg

    for pkg in sorted(npkgs):
        opkg = None
        oreqs = {}
        oobss = {}
        ocons = {}
        if opts.ignore_arch:
            if pkg.name in opkgs:
                opkg = opkgs[pkg.name]
        elif (pkg.name, pkg.arch) in opkgs:
            opkg = opkgs[(pkg.name, pkg.arch)]

        if opkg is None and opts.skip_new:
            continue

        print "New-Package:", pkg, pkg.ui_from_repo

        if opkg is not None:
            print "Old-Package:", opkg, opkg.ui_from_repo

            oreqs = _get_oreqs(pkg, opkg.requires)
            ocons = _get_oreqs(pkg, opkg.conflicts)
            oobss = _get_oreqs(pkg, opkg.obsoletes)

        used_repos_reqs = []
        nreqs, creqs = _get_reqs(pkg, pkg.requires, oreqs)
        if nreqs:
            print "New-Requires:"
            _print_reqs(yb, pkg, nreqs, used_repos_reqs)
        if creqs:
            print "Modified-Requires:"
            _print_reqs(yb, pkg, creqs, used_repos_reqs)

        _print_sum("Dep-Requires-Repos:", used_repos_reqs)

        used_repos_cons = []
        nreqs, creqs = _get_reqs(pkg, pkg.conflicts, ocons)
        if nreqs:
            print "New-Conflicts:"
            _print_reqs(yb, pkg, nreqs, used_repos_cons)
        if creqs:
            print "Mod-Conflicts:"
            _print_reqs(yb, pkg, creqs, used_repos_cons)

        _print_sum("Dep-Conflicts-Repos:", used_repos_cons)

        used_repos_obss = []
        nreqs, creqs = _get_reqs(pkg, pkg.obsoletes, oobss)
        if nreqs:
            print "New-Obsoletes:"
            _print_reqs(yb, pkg, nreqs, used_repos_obss)
        if creqs:
            print "Mod-Obsoletes:"
            _print_reqs(yb, pkg, creqs, used_repos_obss)

        _print_sum("Dep-Obsoletes-Repos:", used_repos_obss)
        _print_sum("Dep-Repos:",
                   used_repos_reqs + used_repos_cons + used_repos_obss,
                   end='')


if __name__ == "__main__":
    yum.misc.setup_locale()
    main()

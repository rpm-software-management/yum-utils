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
## (c) 2008 Red Hat. Written by skvidal@fedoraproject.org
##                                james@fedoraproject.org

import os
import sys
import gzip
import tempfile

from optparse import OptionParser

import yum
import rpmUtils.miscutils

sections = ['%%%%SYSTEM INFO\n', '%%%%YUM INFO\n',
            '%%%%RPMDB PROBLEMS\n', '%%%%RPMDB\n',
            '%%%%REPOS\n']

def cmd_line():
    parser = OptionParser()
    parser.set_usage("yum-debug-restore [options]")
    parser.add_option("-C", "--cache", action="store_true",
                      help="run from cache only")
    parser.add_option("-c", dest="conffile", help="config file location")
    parser.add_option("--enablerepo", action="append", dest="enablerepos",
                      help="specify additional repoids to query, can be specified multiple times")
    parser.add_option("--disablerepo", action="append", dest="disablerepos",
                      help="specify repoids to disable, can be specified multiple times")                      
    parser.add_option("-y", dest="assumeyes", action="store_true",
                      help="answer yes for all questions")
    parser.add_option("--skip-broken", action="store_true",
                      help="skip packages with depsolving problems")

    parser.add_option("--output", action="store_true",
                      help="output the yum shell commands")
    parser.add_option("--shell", 
                      help="output the yum shell commands to a file")

    parser.add_option("--install-latest", action="store_true",
                      help="install the latest instead of specific versions")
    parser.add_option("--ignore-arch", action="store_true",
                      help="ignore arch of packages, so you can dump on .i386 and restore on .x86_64")

    parser.add_option("--filter-types", 
                      help="Limit to: install, remove, update, downgrade")

    (opts, args) = parser.parse_args()
    if not args:
        parser.print_usage()
        sys.exit(1)
    return (opts, args)

class OtherRpmDB:

    def __init__(self, fn):
        self.pkgtups = []

        if fn.endswith(".gz"):
            fo = gzip.GzipFile(fn)
        else:
            fo = open(fn)

        if fo.readline() != 'yum-debug-dump version 1\n':
            print >>sys.stderr, "Bad yum debug file:", fn
            sys.exit(1)

        skip = sections[:-1]
        for line in fo:
            if skip: # Header stuff
                if line == skip[0]:
                    skip.pop(0)
                continue

            if not line or line[0] != ' ':
                break

            pkgtup = rpmUtils.miscutils.splitFilename(line.strip())
            n,v,r,e,a = pkgtup # grrr...
            pkgtup = (n,a,e,v,r)
            self.pkgtups.append(pkgtup)

def naevr2str(n,a,e,v,r):
    if a is None: # Assume epoch doesn't change without release changing
        return "%s-%s-%s" % (n,v,r)
    if e in (None, '', '0'):
        return "%s-%s-%s.%s" % (n,v,r,a)
    return "%s-%s:%s-%s.%s" % (n,e,v,r,a)
def pkgtup2str(pkgtup):
    n,a,e,v,r = pkgtup
    return naevr2str(n,a,e,v,r)

def pkg_data2list(yb, opkgtups, opkgmaps, install_latest, ignore_arch):
    ret = []
    npkgtups = set()
    npkgmaps = {}
    installonly = set(yb.conf.installonlypkgs)
    for po in sorted(yb.rpmdb.returnPackages()):
        arch = po.arch
        if ignore_arch:
            arch = None
        if False: pass
        elif po.name in installonly:
            if not po.pkgtup in opkgtups:
                ret.append(("remove", pkgtup2str(po.pkgtup)))
        elif (po.name, arch) not in opkgmaps:
            ret.append(("remove", str(po)))
        elif po.pkgtup not in opkgtups:
            n,a,e,v,r = opkgmaps[(po.name, arch)]
            pinstEVR = yum.packages.PackageEVR(e, v, r)
            if po.EVR == pinstEVR:
                assert ignore_arch and po.arch != a
            elif po.EVR < pinstEVR:
                ret.append(("upgrade",   naevr2str(n,arch,e,v,r)))
            else:
                ret.append(("downgrade", naevr2str(n,arch,e,v,r)))
        npkgtups.add(po.pkgtup)
        npkgmaps[(po.name, po.arch)] = po
        if ignore_arch:
            npkgmaps[(po.name, None)] = po

    for name, arch in sorted(opkgmaps):
        if name in installonly:
            continue # done separately
        if ignore_arch and arch is not None:
            continue
        if (name, arch) in npkgmaps:
            continue
        if install_latest and ignore_arch:
            ret.append(("install", name))
        elif install_latest:
            ret.append(("install", "%s.%s" % (name, arch)))
        else:
            ret.append(("install", pkgtup2str(opkgmaps[(name, arch)])))
    for pkgtup in opkgtups:
        if pkgtup[0] in installonly and not pkgtup in npkgtups:
            ret.append(("install", pkgtup2str(pkgtup)))
    return ret

def main():
    (opts, args) = cmd_line()
    yb = yum.YumBase()
    yb.preconf.init_plugins = True
    if opts.conffile:
        yb.preconf.fn = opts.conffile

    yb.conf
    if opts.cache:
        yb.conf.cache = True

    if opts.disablerepos:
        for repo_match in opts.disablerepos:
            for repo in yb.repos.findRepos(repo_match):
                repo.disable()

    if opts.enablerepos:    
        for repo_match in opts.enablerepos:
            for repo in yb.repos.findRepos(repo_match):
                repo.enable()

    xtra_args = []
    if opts.skip_broken:
        xtra_args.append('--skip-broken')

    if opts.assumeyes:
        xtra_args.append('-y')

    fn = args[0]
    print "Reading from: %s" % fn
    orpmdb = OtherRpmDB(fn)

    opkgmaps = {}
    for pkgtup in orpmdb.pkgtups:
        opkgmaps[(pkgtup[0], pkgtup[1])] = pkgtup
        if opts.ignore_arch:
            n,a,e,v,r = pkgtup
            opkgmaps[(pkgtup[0], None)] = n,None,e,v,r

    if opts.output:
        fo = sys.stdout
    elif opts.shell:
        try:
            fo = open(opts.shell, "wb")
        except OSError, e:
            print >>sys.stderr, "open(%s): %s" % (opts.shell, e)
            sys.exit(1)
    else:
        fo = tempfile.NamedTemporaryFile()

    fT = None
    if opts.filter_types:
        fT = set(opts.filter_types.replace(",", " ").split())

    counts = {}
    for T, pkg in pkg_data2list(yb, set(orpmdb.pkgtups), opkgmaps,
                                opts.install_latest, opts.ignore_arch):
        if fT is not None and T not in fT:
            continue
        counts[T] = counts.get(T, 0) + 1
        try:
            print >>fo, "%-9s %s" % (T, pkg)
        except IOError:
            if opts.output: # mainly due to |
                sys.exit(1)
            raise

    if opts.output:
        sys.exit(0)

    print >>fo, "run"
    fo.flush()

    if opts.shell:
        if counts:
            print "Statistics:"
        for T in sorted(counts):
            print "    %9s %6u" % (T, counts[T])
        print "Done"
        sys.exit(0)

    # Want to do the transaction, hacky method
    xtra_args.append('--setopt=installonly_limit=0')
    os.system("yum shell %s %s" % (" ".join(xtra_args), fo.name))

if __name__ == "__main__":
    main()



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
# (c) pmatilai@laiskiainen.org


import sys
import signal
import re
import fnmatch
import time
import os
import exceptions

from optparse import OptionParser

import yum
import yum.config
import yum.Errors
import yum.packages
import repomd.mdErrors
from rpmUtils.arch import getArchList
from yum.misc import getCacheDir

version = "0.0.9"

flags = { 'EQ':'=', 'LT':'<', 'LE':'<=', 'GT':'>', 'GE':'>=', 'None':' '}

std_qf = { 
'nvr': '%{name}-%{version}-%{release}',
'nevra': '%{name}-%{epoch}:%{version}-%{release}.%{arch}',
'envra': '%{epoch}:%{name}-%{version}-%{release}.%{arch}',
'source': '%{sourcerpm}',
'info': """
Name        : %{name}
Version     : %{version}
Release     : %{release}
Architecture: %{arch}
Size        : %{installedsize}
Packager    : %{packager}
Group       : %{group}
URL         : %{url}
Repository  : %{repoid}
Summary     : %{summary}
Description :\n%{description}""",
}

querytags = [ 'name', 'version', 'release', 'epoch', 'arch', 'summary',
              'description', 'packager', 'url', 'buildhost', 'sourcerpm',
              'vendor', 'group', 'license', 'buildtime', 'filetime',
              'installedsize', 'archivesize', 'packagesize', 'repoid', 
              'requires', 'provides', 'conflicts', 'obsoletes',
              'relativepath', 'hdrstart', 'hdrend', 'id',
            ]

def sec2date(timestr):
    return time.ctime(int(timestr))

def sec2day(timestr):
    return time.strftime("%a %b %d %Y", time.gmtime(int(timestr)))

convertmap = { 'date': sec2date,
               'day':  sec2day,
             }

def rpmevr(e, v, r):
    et = ""
    vt = ""
    rt = ""
    if e and e != "0":
        et = "%s:" % e
    if v:
        vt = "%s" % v
    if r:
        rt = "-%s" % r
    return "%s%s%s" % (et, vt, rt)

class queryError(exceptions.Exception):
    def __init__(self, msg):
        exceptions.Exception.__init__(self)
        self.msg = msg

class pkgQuery:
    def __init__(self, pkg, qf):
        self.pkg = pkg
        self.qf = qf
        self.name = pkg.name
    
    def __getitem__(self, item):
        if hasattr(self, "fmt_%s" % item):
            return getattr(self, "fmt_%s" % item)()
        res = None
        convert = None

        tmp = item.split(':')
        if len(tmp) > 1:
            item = tmp[0]
            conv = tmp[1]
            if convertmap.has_key(conv):
                convert = convertmap[conv]
            else:
                raise queryError("Invalid conversion: %s" % conv)

        try:
            res = self.pkg.returnSimple(item)
        except KeyError:
            if item == "license":
                res = ", ".join(self.pkg.licenses)
            else:
                raise queryError("Invalid querytag: %s" % item)
        if convert:
            res = convert(res)
        return res

    def __str__(self):
        return self.fmt_queryformat()

    def doQuery(self, method, *args, **kw):
        if std_qf.has_key(method):
            self.qf = std_qf[method]
            return self.fmt_queryformat()
        elif hasattr(self, "fmt_%s" % method):
            return getattr(self, "fmt_%s" % method)(*args, **kw)
        else:
            raise queryError("Invalid package query: %s" % method)

    def _prco(self, what, **kw):
        rpdict = {}
        for rptup in self.pkg.returnPrco(what):
            (rpn, rpf, (rp,rpv,rpr)) = rptup
            # rpmlib deps should be handled on their own
            if rpn[:6] == 'rpmlib':
                continue
            if rpf:
                rpdict["%s %s %s" % (rpn, flags[rpf], rpmevr(rp,rpv,rpr))] = None
            else:
                rpdict[rpn] = None
        return rpdict.keys()

    # these return formatted strings, not lists..
    def fmt_queryformat(self):

        if not self.qf:
            qf = std_qf["nevra"]
        else:
            qf = self.qf

        qf = qf.replace("\\n", "\n")
        qf = qf.replace("\\t", "\t")
        pattern = re.compile('%([-\d]*?){([:\w]*?)}')
        fmt = re.sub(pattern, r'%(\2)\1s', qf)
        return fmt % self

    def fmt_list(self, **kw):
        fdict = {}
        for file in self.pkg.returnFileEntries():
            fdict[file] = None
        files = fdict.keys()
        files.sort()
        return "\n".join(files)

    def fmt_changelog(self, **kw):
        changelog = []
        for date, author, message in self.pkg.returnChangelog():
            changelog.append("* %s %s\n%s\n" % (sec2day(date), author, message))
        return "\n".join(changelog)

    def fmt_obsoletes(self, **kw):
        return "\n".join(self._prco("obsoletes"))

    def fmt_provides(self, **kw):
        return "\n".join(self._prco("provides"))

    def fmt_requires(self, **kw):
        return "\n".join(self._prco("requires"))

    def fmt_conflicts(self, **kw):
        return "\n".join(self._prco("conflicts"))

class groupQuery:
    def __init__(self, groupinfo, name, grouppkgs="required"):
        self.groupInfo = groupinfo
        self.grouppkgs = grouppkgs
        self.name = name
        self.group = groupinfo.group_by_id[name]

    def doQuery(self, method, *args, **kw):
        if hasattr(self, "fmt_%s" % method):
            return "\n".join(getattr(self, "fmt_%s" % method)(*args, **kw))
        else:
            raise queryError("Invalid group query: %s" % method)

    # XXX temporary hack to make --group -a query work
    def fmt_queryformat(self):
        return self.fmt_nevra()

    def fmt_nevra(self):
        return ["%s - %s" % (self.group.id, self.group.name)]

    def fmt_list(self):
        pkgs = []
        for t in self.grouppkgs.split(','):
            if t == "required":
                pkgs.extend(self.groupInfo.requiredPkgs(self.name))
            elif t == "mandatory":
                pkgs.extend(self.groupInfo.mandatory_pkgs[self.name])
            elif t == "default":
                pkgs.extend(self.groupInfo.default_pkgs[self.name])
            elif t == "optional":
                pkgs.extend(self.groupInfo.optional_pkgs[self.name])
            elif t == "all":
                pkgs.extend(self.groupInfo.allPkgs(self.name))
            else:
                raise "Unknown group package type %s" % t
            
        return pkgs
        
    def fmt_requires(self):
        return self.groupInfo.requiredGroups(self.name)

    def fmt_info(self):
        return ["%s:\n\n%s\n" % (self.group.name, self.group.description)]

class YumBaseQuery(yum.YumBase):
    def __init__(self, pkgops = [], sackops = [], options = None):
        yum.YumBase.__init__(self)
        self.conf = yum.config.yumconf()
        self.options = options
        self.pkgops = pkgops
        self.sackops = sackops

    # dont log anything..
    def log(self, value, msg):
        pass

    def errorlog(self, value, msg):
        if not self.options.quiet:
            print >> sys.stderr, msg

    def queryPkgFactory(self, pkgs):
        qf = self.options.queryformat or std_qf["nevra"]
        qpkgs = []
        for pkg in pkgs:
            qpkg = pkgQuery(pkg, qf)
            qpkgs.append(qpkg)
        return qpkgs

    def returnNewestByName(self, name):
        pkgs = []
        try:
            exact, match, unmatch = yum.packages.parsePackages(self.pkgSack.returnPackages(), [name], casematch=1)
            pkgs = exact + match
        except repomd.mdErrors.PackageSackError, err:
            self.errorlog(0, err)
        return self.queryPkgFactory(pkgs)

    def returnPackagesByDep(self, depstring):
        provider = []
        try:
            provider.extend(yum.YumBase.returnPackagesByDep(self, depstring))
        except yum.Errors.YumBaseError, err:
            self.errorlog(0, "No package provides %s" % depstring)
        return self.queryPkgFactory(provider)

    def returnGroups(self):
        grps = []
        for name in self.groupInfo.grouplist:
            grp = groupQuery(self.groupInfo, name, 
                             grouppkgs = self.options.grouppkgs)
            grps.append(grp)
        return grps

    def matchGroups(self, items):
        if not items:
            return self.returnGroups()
        grps = []
        for grp in self.returnGroups():
            for expr in items:
                if grp.name == expr or fnmatch.fnmatch("%s" % grp.name, expr):
                    grps.append(grp)
        return grps
                    
            
    def matchPkgs(self, items):
        if not items:
            return self.queryPkgFactory(self.pkgSack.returnPackages())
        
        pkgs = []
        notfound = {}
        
        exact, match, unmatch = yum.packages.parsePackages(self.pkgSack.returnPackages(),
                                           items, casematch=1)
        pkgs = exact + match
        notfound = unmatch

        return self.queryPkgFactory(pkgs)

    def runQuery(self, items):
        if self.options.group:
            pkgs = self.matchGroups(items)
        else:
            pkgs = self.matchPkgs(items)

        for pkg in pkgs:
            for oper in self.pkgops:
                try:
                    print pkg.doQuery(oper)
                except queryError, e:
                    self.errorlog(0, e.msg)
        for prco in items:
            for oper in self.sackops:
                try:
                    for p in self.doQuery(oper, prco): print p
                except queryError, e:
                    self.errorlog(0, e.msg)

    def doQuery(self, method, *args, **kw):
        return getattr(self, method)(*args, **kw)

    def groupmember(self, name, **kw):
        grps = []
        for id in self.groupInfo.grouplist:
            if name in self.groupInfo.allPkgs(id):
                grps.append(id)
        return grps

    def whatprovides(self, name, **kw):
        return self.returnPackagesByDep(name)

    def whatrequires(self, name, **kw):
        pkgs = {}
        provs = [name]
                
        if self.options.alldeps:
            for pkg in self.returnNewestByName(name):
                provs.extend(pkg._prco("provides"))

        for prov in provs:
            for pkg in self.pkgSack.searchRequires(prov):
                pkgs[pkg.pkgtup] = pkg
        return self.queryPkgFactory(pkgs.values())

    def requires(self, name, **kw):
        pkgs = {}
        
        for pkg in self.returnNewestByName(name):
            for req in pkg._prco("requires"):
                for res in self.whatprovides(req):
                    pkgs[res.name] = res
        return pkgs.values()

    def location(self, name):
        loc = []
        for pkg in self.returnNewestByName(name):
            repo = self.repos.getRepo(pkg['repoid'])
            loc.append("%s/%s" % (repo.urls[0], pkg['relativepath']))
        return loc

def main(args):

    needfiles = 0
    needother = 0
    needgroup = 0

    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    parser = OptionParser()
    # query options
    parser.add_option("-l", "--list", default=0, action="store_true",
                      help="list files in this package/group")
    parser.add_option("-i", "--info", default=0, action="store_true",
                      help="list descriptive info from this package/group")
    parser.add_option("-f", "--file", default=0, action="store_true",
                      help="query which package provides this file")
    parser.add_option("--qf", "--queryformat", dest="queryformat",
                      help="specify a custom output format for queries")
    parser.add_option("--groupmember", default=0, action="store_true",
                      help="list which group(s) this package belongs to")
    # dummy for rpmq compatibility
    parser.add_option("-q", "--query", default=0, action="store_true",
                      help="no-op for rpmquery compatibility")
    parser.add_option("-a", "--all", default=0, action="store_true",
                      help="query all packages/groups")
    parser.add_option("--requires", default=0, action="store_true",
                      help="list package dependencies")
    parser.add_option("--provides", default=0, action="store_true",
                      help="list capabilities this package provides")
    parser.add_option("--obsoletes", default=0, action="store_true",
                      help="list other packages obsoleted by this package")
    parser.add_option("--conflicts", default=0, action="store_true",
                      help="list capabilities this package conflicts with")
    parser.add_option("--changelog", default=0, action="store_true",
                      help="show changelog for this package")
    parser.add_option("--location", default=0, action="store_true",
                      help="show download URL for this package")
    parser.add_option("--nevra", default=0, action="store_true",
                      help="show name-epoch:version-release.architecture info of package")
    parser.add_option("--envra", default=0, action="store_true",
                      help="show epoch:name-version-release.architecture info of package")
    parser.add_option("--nvr", default=0, action="store_true",
                      help="show name, version, release info of package")
    parser.add_option("-s", "--source", default=0, action="store_true",
                      help="show package source RPM name")
    parser.add_option("--resolve", default=0, action="store_true",
                      help="resolve capabilities to originating package(s)")
    parser.add_option("--alldeps", default=0, action="store_true",
                      help="check non-explicit dependencies as well")
    parser.add_option("--whatprovides", default=0, action="store_true",
                      help="query what package(s) provide a capability")
    parser.add_option("--whatrequires", default=0, action="store_true",
                      help="query what package(s) require a capability")
    # group stuff
    parser.add_option("--group", default=0, action="store_true", 
                      help="query groups instead of packages")
    parser.add_option("--grouppkgs", default="required", dest="grouppkgs",
                      help="filter which packages (all,optional etc) are shown from groups")
    # other opts
    parser.add_option("", "--repoid", default=[], action="append",
                      help="specify repoids to query, can be specified multiple times (default is all enabled)")
    parser.add_option("-v", "--version", default=0, action="store_true",
                      help="show program version and exit")
    parser.add_option("--quiet", default=0, action="store_true", 
                      help="quiet (no output to stderr)")
    parser.add_option("-C", "--cache", default=0, action="store_true",
                      help="run from cache only")
    parser.add_option("--tempcache", default=0, action="store_true",
                      help="use private cache (default when used as non-root)")
    parser.add_option("--querytags", default=0, action="store_true",
                      help="list available tags in queryformat queries")

    (opts, regexs) = parser.parse_args()
    if opts.version:
        print "Repoquery version %s" % version
        sys.exit(0)
    if opts.querytags:
        querytags.sort()
        for tag in querytags:
            print tag
        sys.exit(0)

    if len(regexs) < 1 and not opts.all:
        parser.print_help()
        sys.exit(1)

    pkgops = []
    sackops = []
    archlist = None
    if opts.requires:
        if opts.resolve:
            sackops.append("requires")
        else:
            pkgops.append("requires")
    if opts.provides:
        pkgops.append("provides")
    if opts.obsoletes:
        pkgops.append("obsoletes")
    if opts.conflicts:
        pkgops.append("conflicts")
    if opts.changelog:
        needother = 1
        pkgops.append("changelog")
    if opts.list:
        if not opts.group:
            needfiles = 1
        pkgops.append("list")
    if opts.info:
        pkgops.append("info")
    if opts.envra:
        pkgops.append("envra")
    if opts.nvr:
        pkgops.append("nvr")
    if opts.source:
        pkgops.append("source")
    if opts.whatrequires:
        sackops.append("whatrequires")
    if opts.whatprovides:
        sackops.append("whatprovides")
    if opts.file:
        sackops.append("whatprovides")
    if opts.location:
        sackops.append("location")
    if opts.groupmember:
        sackops.append("groupmember")
        needgroup = 1
    if opts.group:
        needgroup = 1

    if opts.nevra or (len(pkgops) == 0 and len(sackops) == 0):
        pkgops.append("queryformat")

    repoq = YumBaseQuery(pkgops, sackops, opts)
    repoq.doConfigSetup()
    
    if os.geteuid() != 0 or opts.tempcache:
        cachedir = getCacheDir()
        if cachedir is None:
            repoq.errorlog("0, Error: Could not make cachedir, exiting")
            sys.exit(50)
        repoq.repos.setCacheDir(cachedir)

    if opts.cache:
        repoq.conf.setConfigOption('cache', 1)
        repoq.errorlog(0, 'Running from cache, results might be incomplete.')
    
    if len(opts.repoid) > 0:
        for repo in repoq.repos.findRepos('*'):
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                repo.enable()

    repoq.doRepoSetup()

    for exp in regexs:
        if exp.endswith('.src'):
            archlist = getArchList()
            archlist.append('src')
            break
    
    try:
        repoq.doSackSetup(archlist=archlist)
        if needfiles:
            repoq.repos.populateSack(with='filelists')
        if needother:
            repoq.repos.populateSack(with='otherdata')
        if needgroup:
            repoq.doTsSetup()
            repoq.doGroupSetup()
    except yum.Errors.RepoError, e:
        repoq.errorlog(1, e)
        sys.exit(1)

    repoq.runQuery(regexs)

if __name__ == "__main__":
    main(sys.argv)
                
# vim:sw=4:sts=4:expandtab              

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
from rpmUtils.arch import getArchList
from rpmUtils.miscutils import formatRequire
from yum.misc import getCacheDir

version = "0.0.11"

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

# abstract class
class pkgQuery:
    def __init__(self, pkg, qf):
        self.pkg = pkg
        self.qf = qf
        self.name = pkg.name
        self.classname = None
    
    def __getitem__(self, item):
        item = item.lower()
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

        # this construct is the way it is because pkg.licenses isn't
        # populated before calling pkg.returnSimple() ?!
        try:
            res = self.pkg.returnSimple(item)
        except KeyError:
            if item == "license":
                res = ", ".join(self.pkg.licenses)
            else:
                raise queryError("Invalid querytag '%s' for %s" % (item, self.classname))
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

    def fmt_requires(self, **kw):
        return "\n".join(self.prco('requires'))

    def fmt_provides(self, **kw):
        return "\n".join(self.prco('provides'))

    def fmt_conflicts(self, **kw):
        return "\n".join(self.prco('conflicts'))

    def fmt_obsoletes(self, **kw):
        return "\n".join(self.prco('obsoletes'))

class repoPkgQuery(pkgQuery):
    def __init__(self, pkg, qf):
        pkgQuery.__init__(self, pkg, qf)
        self.classname = 'repo pkg'

    def prco(self, what, **kw):
        rpdict = {}
        for rptup in self.pkg.returnPrco(what):
            (rpn, rpf, (rp,rpv,rpr)) = rptup
            if rpn.startswith('rpmlib'):
                continue
            rpdict[self.pkg.prcoPrintable(rptup)] = None
    
        rplist = rpdict.keys()
        rplist.sort()
        return rplist

    def fmt_list(self, **kw):
        fdict = {}
        for ftype in self.pkg.returnFileTypes():
            for file in self.pkg.returnFileEntries(ftype):
                # workaround for yum returning double leading slashes on some 
                # directories - posix allows that but it looks a bit odd
                fdict[os.path.normpath('//%s' % file)] = None
        files = fdict.keys()
        files.sort()
        return "\n".join(files)

    def fmt_changelog(self, **kw):
        changelog = []
        for date, author, message in self.pkg.returnChangelog():
            changelog.append("* %s %s\n%s\n" % (sec2day(date), author, message))
        return "\n".join(changelog)

class instPkgQuery(pkgQuery):
    # hmm, thought there'd be more things in need of mapping to rpm names :)
    tagmap = { 'installedsize': 'size',
             }

    def __init__(self, pkg, qf):
        pkgQuery.__init__(self, pkg, qf)
        self.classname = 'installed pkg'

    def __getitem__(self, item):
        if self.tagmap.has_key(item):
            return self.pkg.tagByName(self.tagmap[item])
        else:
            return pkgQuery.__getitem__(self, item)
            
    def prco(self, what, **kw):
        prcodict = {}
        # rpm names are without the trailing s :)
        what = what[:-1]

        names = self.pkg.tagByName('%sname' % what)
        flags = self.pkg.tagByName('%sflags' % what)
        ver = self.pkg.tagByName('%sversion' % what)
        if names is not None:
            for (n, f, v) in zip(names, flags, ver):
                req = formatRequire(n, v, f)
                # filter out rpmlib deps
                if n.startswith('rpmlib'):
                    continue
                prcodict[req] = None

        prcolist = prcodict.keys()
        prcolist.sort()
        return prcolist
    
    def fmt_list(self, **kw):
        return "\n".join(self.pkg.tagByName('filenames'))

    def fmt_changelog(self, **kw):
        changelog = []
        times = self.pkg.tagByName('changelogtime')
        names = self.pkg.tagByName('changelogname')
        texts = self.pkg.tagByName('changelogtext')
        if times is not None:
            tmplst = zip(times, names, texts)

            for date, author, message in zip(times, names, texts):
                changelog.append("* %s %s\n%s\n" % (sec2day(date), author, message))
        return "\n".join(changelog)


class groupQuery:
    def __init__(self, group, grouppkgs="required"):
        self.grouppkgs = grouppkgs
        self.id = group.groupid
        self.name = group.name
        self.group = group

    def doQuery(self, method, *args, **kw):
        if hasattr(self, "fmt_%s" % method):
            return "\n".join(getattr(self, "fmt_%s" % method)(*args, **kw))
        else:
            raise queryError("Invalid group query: %s" % method)

    # XXX temporary hack to make --group -a query work
    def fmt_queryformat(self):
        return self.fmt_nevra()

    def fmt_nevra(self):
        return ["%s - %s" % (self.id, self.name)]

    def fmt_list(self):
        pkgs = []
        for t in self.grouppkgs.split(','):
            if t == "mandatory":
                pkgs.extend(self.group.mandatory_packages)
            elif t == "default":
                pkgs.extend(self.group.default_packages)
            elif t == "optional":
                pkgs.extend(self.group.optional_packages)
            elif t == "all":
                pkgs.extend(self.group.packages)
            else:
                raise "Unknown group package type %s" % t
            
        return pkgs
        
    def fmt_requires(self):
        return self.group.mandatory_packages

    def fmt_info(self):
        return ["%s:\n\n%s\n" % (self.name, self.group.description)]

class YumBaseQuery(yum.YumBase):
    def __init__(self, pkgops = [], sackops = [], options = None):
        yum.YumBase.__init__(self)
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
            if isinstance(pkg, yum.packages.YumInstalledPackage):
                qpkg = instPkgQuery(pkg, qf)
            else:
                qpkg = repoPkgQuery(pkg, qf)
            qpkgs.append(qpkg)
        return qpkgs

    def returnByName(self, name):
        pkgs = []
        try:
            exact, match, unmatch = yum.packages.parsePackages(self.returnPkgList(), [name], casematch=1)
            pkgs = exact + match
        except yum.Errors.PackageSackError, err:
            self.errorlog(0, err)
        return self.queryPkgFactory(pkgs)

    def returnPkgList(self):
        pkgs = []
        if self.options.pkgnarrow == "repos":
            if self.conf.showdupesfromrepos:
                pkgs = self.pkgSack.returnPackages()
            else:
                pkgs = self.pkgSack.returnNewestByNameArch()

        else:
            what = self.options.pkgnarrow
            ygh = self.doPackageLists(what)

            if what == "all":
                pkgs = ygh.available + ygh.installed
            elif hasattr(ygh, what):
                pkgs = getattr(ygh, what)
            else:
                self.errorlog(1, "Unknown pkgnarrow method: %s" % what)

        return pkgs
    
    def returnPackagesByDep(self, depstring):
        provider = []
        try:
            provider.extend(yum.YumBase.returnPackagesByDep(self, depstring))
        except yum.Errors.YumBaseError, err:
            self.errorlog(0, "No package provides %s" % depstring)
        return self.queryPkgFactory(provider)

    def returnGroups(self):
        grps = []
        for group in self.comps.get_groups():
            grp = groupQuery(group, grouppkgs = self.options.grouppkgs)
            grps.append(grp)
        return grps

    def matchGroups(self, items):
        grps = []
        for grp in self.returnGroups():
            for expr in items:
                if grp.name == expr or fnmatch.fnmatch("%s" % grp.name, expr):
                    grps.append(grp)
                elif grp.id == expr or fnmatch.fnmatch("%s" % grp.id, expr):
                    grps.append(grp)
        return grps
                    
    def matchPkgs(self, items):
        pkgs = []
        notfound = {}
        
        exact, match, unmatch = yum.packages.parsePackages(self.returnPkgList(),
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
        return getattr(self, "fmt_%s" % method)(*args, **kw)

    def fmt_groupmember(self, name, **kw):
        grps = []
        for group in self.comps.get_groups():
            if name in group.packages:
                grps.append(group.groupid)
        return grps

    def fmt_whatprovides(self, name, **kw):
        return self.returnPackagesByDep(name)

    def fmt_whatrequires(self, name, **kw):
        pkgs = {}
        provs = [name]
                
        if self.options.alldeps:
            for pkg in self.returnByName(name):
                provs.extend(pkg.prco("provides"))

        for prov in provs:
            # Only look at the providing name, not the whole version. This 
            # might occasionally give some false positives but that's 
            # better than missing ones which it had previously
            for pkg in self.pkgSack.searchRequires(prov.split()[0]):
                pkgs[pkg.pkgtup] = pkg
        return self.queryPkgFactory(pkgs.values())

    def fmt_whatobsoletes(self, name, **kw):
        pkgs = []
        for pkg in self.pkgSack.searchObsoletes(name):
            pkgs.append(pkg)
        return self.queryPkgFactory(pkgs)
            
    def fmt_whatconflicts(self, name, **kw):
        pkgs = []
        for pkg in self.pkgSack.searchConflicts(name):
            pkgs.append(pkg)
        return self.queryPkgFactory(pkgs)

    def fmt_requires(self, name, **kw):
        pkgs = {}
        
        for pkg in self.returnByName(name):
            for req in pkg.prco("requires"):
                for res in self.fmt_whatprovides(req):
                    pkgs[res.name] = res
        return pkgs.values()

    def fmt_location(self, name):
        loc = []
        for pkg in self.returnByName(name):
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
    parser.add_option("--whatobsoletes", default=0, action="store_true",
                      help="query what package(s) obsolete a capability")
    parser.add_option("--whatconflicts", default=0, action="store_true",
                      help="query what package(s) conflicts with a capability")
    # group stuff
    parser.add_option("-g", "--group", default=0, action="store_true", 
                      help="query groups instead of packages")
    parser.add_option("--grouppkgs", default="default", dest="grouppkgs",
                      help="filter which packages (all,optional etc) are shown from groups")
    # other opts
    parser.add_option("--archlist", dest="archlist", 
                      help="only query packages of certain architecture(s)")
    parser.add_option("--pkgnarrow", default="repos", dest="pkgnarrow",
                      help="limit query to installed / available / recent / updates / extras / available + installed / repository (default) packages")
    parser.add_option("--show-dupes", default=0, action="store_true",
                      help="show all versions of packages")
    parser.add_option("--repoid", default=[], action="append",
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
    parser.add_option("-c", dest="conffile", action="store",
                      default='/etc/yum.conf', help="config file location")

    (opts, regexs) = parser.parse_args()
    if opts.version:
        print "Repoquery version %s" % version
        sys.exit(0)
    if opts.querytags:
        querytags.sort()
        for tag in querytags:
            print tag
        sys.exit(0)

    if len(regexs) < 1:
        if opts.all:
            regexs = ['*']
        else:
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
    if opts.whatobsoletes:
        sackops.append("whatobsoletes")
    if opts.whatconflicts:
        sackops.append("whatconflicts")
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
    repoq.doStartupConfig(fn=opts.conffile)
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

    if opts.show_dupes:
        repoq.conf.setConfigOption('showdupesfromrepos', 1)

    if len(opts.repoid) > 0:
        for repo in repoq.repos.findRepos('*'):
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                repo.enable()

    repoq.doRepoSetup()

    if opts.archlist:
        archlist = opts.archlist.split(',')
    else:
        for exp in regexs:
            if exp.endswith('.src'):
                archlist = getArchList()
                archlist.append('src')
                break

    try:
        repoq.doSackSetup(archlist=archlist)
        repoq.doTsSetup()
        if needfiles:
            repoq.repos.populateSack(with='filelists')
        if needother:
            repoq.repos.populateSack(with='otherdata')
        if needgroup:
            repoq.doGroupSetup()
    except yum.Errors.RepoError, e:
        repoq.errorlog(1, e)
        sys.exit(1)

    repoq.runQuery(regexs)

if __name__ == "__main__":
    main(sys.argv)
                
# vim:sw=4:sts=4:expandtab              

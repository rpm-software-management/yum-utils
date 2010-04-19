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
sys.path.insert(0, '/usr/share/yum-cli')

import signal
import re
import fnmatch
import time
import os
import os.path
import exceptions
import urlparse

from optparse import OptionParser

import logging
import yum
import yum.misc as misc
import yum.config
import yum.Errors
import yum.packages
from yum.i18n import to_unicode
from rpmUtils.arch import getArchList
from rpmUtils.miscutils import formatRequire
import output
from urlgrabber.progress import TextMeter
from urlgrabber.progress import format_number

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

def sec2isodate(timestr):
    return time.strftime("%F %T", time.gmtime(int(timestr)))

def sec2date(timestr):
    return to_unicode(time.ctime(int(timestr)))

def sec2day(timestr):
    return to_unicode(time.strftime("%a %b %d %Y", time.gmtime(int(timestr))))

def _size2val(size, off, ui):
    size = float(size)
    off = 1024
    if False: pass
    elif size >= (off * 100):
        return "%.0f%s" % ((size / off), ui)
    elif size >= (off *  10):
        return "%.1f%s" % ((size / off), ui)
    return "%.2f%s" % ((size / off), ui)
def size2k(size):
    return _size2val(size,                      1024, " k")
def size2m(size):
    return _size2val(size,               1024 * 1024, " M")
def size2g(size):
    return _size2val(size,        1024 * 1024 * 1024, " G")
def size2t(size):
    return _size2val(size, 1024 * 1024 * 1024 * 1024, " T")
def size2h(size):
    return format_number(size)

convertmap = { 'date': sec2date,
               'day':  sec2day,
               'isodate':  sec2isodate,
               'k':  size2k,
               'm':  size2m,
               'g':  size2g,
               'h':  size2h,
             }

class queryError(exceptions.Exception):
    def __init__(self, msg):
        exceptions.Exception.__init__(self)
        self.msg = msg

# abstract class
class pkgQuery:
    """
    My implementation of __getitem__ either forwards to an implementation
    of fmt_(name), or to self.pkg.returnSimple(), allowing subclasses
    to override the package's items.

    @type pkg: L{yum.package.YumAvailablePackage}
    @ivar qf:  the query format for this package query
    @type qf:  str
    """

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
            if conv in convertmap:
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
        if method in std_qf:
            self.qf = std_qf[method]
            return self.fmt_queryformat()
        elif hasattr(self, "fmt_%s" % method):
            return getattr(self, "fmt_%s" % method)(*args, **kw)
        else:
            raise queryError("Invalid package query: %s" % method)

    def isSource(self):
        return self["arch"] == "src"

    def prco(self, what, **kw):
        """
        Query for the provides/requires/conflicts/obsoletes of this package.

        @param what: one of provides, requires, conflicts, obsoletes
        @type  what: str

        @rtype: list of str
        """
        # for subclasses to implement
        raise NotImplementedError

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

    def fmt_list(self, **kw):
        return "\n".join(self.files())

    def fmt_evr(self, **kw):
        return "%(epoch)s:%(version)s-%(release)s" % self
    def fmt_nevr(self, **kw):
        return "%(name)s-%(evr)s" % self
    def fmt_envr(self, **kw):
        return "%(epoch)s:%(name)s-%(version)s-%(release)s" % self
    def fmt_nevra(self, **kw):
        return "%(nevr)s.%(arch)s" % self
    def fmt_envra(self, **kw):
        return "%(envr)s.%(arch)s" % self

    def fmt_location(self, **kw):
        loc = ''
        repo = self.pkg.repo
        if self['basepath']:
            loc = "%(basepath)s/%(relativepath)s" % self
        else:
            repourl = repo.urls[0]
            if repourl[-1] != '/':
                repourl = repourl + '/'
            loc = urlparse.urljoin(repourl, self['relativepath'])
        return loc

class repoPkgQuery(pkgQuery):
    """
    I wrap a query of a non-installed package available in the repository.
    """
    def __init__(self, pkg, qf):
        pkgQuery.__init__(self, pkg, qf)
        self.classname = 'repo pkg'

    def prco(self, what, **kw):
        rpdict = {}
        for rptup in self.pkg.returnPrco(what):
            (rpn, rpf, (rp,rpv,rpr)) = rptup
            if rpn.startswith('rpmlib'):
                continue
            rpdict[misc.prco_tuple_to_string(rptup)] = None
    
        rplist = rpdict.keys()
        rplist.sort()
        return rplist

    def files(self, **kw):
        fdict = {}
        for ftype in self.pkg.returnFileTypes():
            for fn in self.pkg.returnFileEntries(ftype):
                # workaround for yum returning double leading slashes on some 
                # directories - posix allows that but it looks a bit odd
                fdict[os.path.normpath('//%s' % fn)] = None
        files = fdict.keys()
        files.sort()
        return files

    def fmt_changelog(self, **kw):
        changelog = []
        for date, author, message in self.pkg.returnChangelog():
            changelog.append("* %s %s\n%s\n" % (sec2day(date),
                                                to_unicode(author),
                                                to_unicode(message)))
        return "\n".join(changelog)

class instPkgQuery(pkgQuery):
    """
    I wrap a query of an installed package 
    of type L{yum.packages.YumInstalledPackage}
    """
    # hmm, thought there'd be more things in need of mapping to rpm names :)
    tagmap = { 'installedsize': 'size',
             }

    def __init__(self, pkg, qf):
        pkgQuery.__init__(self, pkg, qf)
        self.classname = 'installed pkg'

    def __getitem__(self, item):
        if item in self.tagmap:
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
    
    def files(self, **kw):
        return self.pkg.tagByName('filenames')

    def fmt_changelog(self, **kw):
        changelog = []
        times = self.pkg.tagByName('changelogtime')
        if times is not None:
            names = self.pkg.tagByName('changelogname')
            texts = self.pkg.tagByName('changelogtext')
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
                raise queryError("Unknown group package type %s" % t)
            
        return pkgs
        
    def fmt_requires(self):
        return self.group.mandatory_packages

    def fmt_info(self):
        return ["%s:\n\n%s\n" % (self.name, self.group.description)]

class YumBaseQuery(yum.YumBase):
    def __init__(self, pkgops = [], sackops = [], options = None):
        """
        @type  pkgops:  list of str
        @type  sackops: list of str
        @type  options: L{optparse.Values}
        """
        yum.YumBase.__init__(self)
        self.logger = logging.getLogger("yum.verbose.repoquery")
        console_stderr = logging.StreamHandler(sys.stderr)
        console_stderr.setFormatter(logging.Formatter("%(message)s"))
        self.logger.propagate = False
        self.logger.addHandler(console_stderr)
        self.options = options
        self.pkgops = pkgops
        self.sackops = sackops

    def queryPkgFactory(self, pkgs):
        """
        For each given package, create a query.

        @type  pkgs: list of L{yum.package.YumAvailablePackage}

        @rtype: list of L{queryPkg}
        """
        qf = self.options.queryformat or std_qf["nevra"]
        qpkgs = []
        for pkg in pkgs:
            if isinstance(pkg, yum.packages.YumInstalledPackage):
                if self.options.pkgnarrow not in ('all', 'installed', 'extras'):
                    continue
                qpkg = instPkgQuery(pkg, qf)
            else:
                qpkg = repoPkgQuery(pkg, qf)
            qpkgs.append(qpkg)
        return qpkgs

    def returnByName(self, name):
        """
        Given a name, return a list of package queries matching the name.

        @type  name: str

        @rtype: list of L{queryPkg}
        """
        pkgs = []
        try:
            pkgs = self.returnPkgList(patterns=[name])
        except yum.Errors.PackageSackError, err:
            self.logger.error(err)
        return self.queryPkgFactory(pkgs)

    def returnPkgList(self, **kwargs):
        pkgs = []
        if self.options.pkgnarrow == "repos":
            # self.pkgSack is a yum.packageSack.MetaSack
            if self.conf.showdupesfromrepos:
                pkgs = self.pkgSack.returnPackages(**kwargs)
            else:
                try:
                    pkgs = self.pkgSack.returnNewestByNameArch(**kwargs)
                except yum.Errors.PackageSackError:
                    pkgs = []
        else:
            what = self.options.pkgnarrow
            ygh = self.doPackageLists(what, **kwargs)

            if what == "all":
                pkgs = ygh.available + ygh.installed
            elif hasattr(ygh, what):
                pkgs = getattr(ygh, what)
            else:
                self.logger.error("Unknown pkgnarrow method: %s" % what)

        return pkgs

    def returnPackagesByDepStr(self, depstring):
        provider = []
        try:
            # XXX rhbz#246519, for some reason returnPackagesByDep() fails
            # to find some root level directories while 
            # searchPackageProvides() does... use that for now
            matches = yum.YumBase.searchPackageProvides(self, [str(depstring)])
            provider = matches.keys()
            # provider.extend(yum.YumBase.returnPackagesByDep(self, depstring))
        except yum.Errors.YumBaseError, err:
            self.logger.error("No package provides %s" % depstring)
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
        pkgs = self.returnPkgList(patterns=items)
        return self.queryPkgFactory(pkgs)

    def matchSrcPkgs(self, items):
        srpms = []
        for name in items:
            for pkg in self.returnByName(name):
                if pkg.isSource(): 
                    continue
                src = pkg["sourcerpm"][:-4]
                srpms.extend(self.returnByName(src))
        return srpms
    
    def runQuery(self, items):
        if self.options.group:
            pkgs = self.matchGroups(items)
        else:
            if self.options.srpm:
                pkgs = self.matchSrcPkgs(items)

            else:
                pkgs = self.matchPkgs(items)
                for prco in items:
                    for oper in self.sackops:
                        try:
                            for p in self.doQuery(oper, prco): 
                                if p:
                                    pkgs.append(p)
                        except queryError, e:
                            self.logger.error( e.msg)

        for pkg in pkgs:
            if not self.pkgops:
                print to_unicode(pkg)
            for oper in self.pkgops:
                try:
                    out = pkg.doQuery(oper)
                    if out:
                        print to_unicode(out)
                except queryError, e:
                    self.logger.error( e.msg)

    def doQuery(self, method, *args, **kw):
        return getattr(self, "fmt_%s" % method)(*args, **kw)

    def fmt_groupmember(self, name, **kw):
        grps = []
        for group in self.comps.get_groups():
            if name in group.packages:
                grps.append(group.groupid)
        return grps

    def fmt_whatprovides(self, name, **kw):
        return self.returnPackagesByDepStr(name)

    def fmt_whatrequires(self, name, **kw):
        pkgs = {}
        done = [] # keep track of names we have already visited

        def require_recursive(name):
            if name in done:
                return
            done.append(name)

            provs = [name]
                    
            if self.options.alldeps:
                for pkg in self.returnByName(name):
                    provs.extend(pkg.prco("provides"))
                    provs.extend(pkg.files())

            for prov in provs:
                for pkg in self.pkgSack.searchRequires(prov):
                    pkgs[pkg.pkgtup] = pkg
                    if self.options.recursive:
                        require_recursive(pkg.name)

        require_recursive(name)
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
            if pkg['basepath']:
                loc.append("%s/%s" % (pkg['basepath'], pkg['relativepath']))
            else:
                loc.append("%s/%s" % (repo.urls[0], pkg['relativepath']))
        return loc

def main(args):

    needfiles = 0
    needother = 0
    needgroup = 0
    needsource = 0

    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    parser = OptionParser(version = "Repoquery version %s" % version)
    # query options
    parser.add_option("-l", "--list", action="store_true",
                      help="list files in this package/group")
    parser.add_option("-i", "--info", action="store_true",
                      help="list descriptive info from this package/group")
    parser.add_option("-f", "--file", action="store_true",
                      help="query which package provides this file")
    parser.add_option("--qf", "--queryformat", dest="queryformat",
                      help="specify a custom output format for queries")
    parser.add_option("--groupmember", action="store_true",
                      help="list which group(s) this package belongs to")
    # dummy for rpmq compatibility
    parser.add_option("-q", "--query", action="store_true",
                      help="no-op for rpmquery compatibility")
    parser.add_option("-a", "--all", action="store_true",
                      help="query all packages/groups")
    parser.add_option("-R", "--requires", action="store_true",
                      help="list package dependencies")
    parser.add_option("--provides", action="store_true",
                      help="list capabilities this package provides")
    parser.add_option("--obsoletes", action="store_true",
                      help="list other packages obsoleted by this package")
    parser.add_option("--conflicts", action="store_true",
                      help="list capabilities this package conflicts with")
    parser.add_option("--changelog", action="store_true",
                      help="show changelog for this package")
    parser.add_option("--location", action="store_true",
                      help="show download URL for this package")
    parser.add_option("--nevra", action="store_true",
                      help="show name-epoch:version-release.architecture info of package")
    parser.add_option("--envra", action="store_true",
                      help="show epoch:name-version-release.architecture info of package")
    parser.add_option("--nvr", action="store_true",
                      help="show name, version, release info of package")
    parser.add_option("-s", "--source", action="store_true",
                      help="show package source RPM name")
    parser.add_option("--srpm", action="store_true",
                      help="operate on corresponding source RPM")
    parser.add_option("--resolve", action="store_true",
                      help="resolve capabilities to originating package(s)")
    parser.add_option("--alldeps", action="store_true", default=True,
                      help="check non-explicit dependencies (files and Provides:) as well, defaults to on")
    parser.add_option("--exactdeps", dest="alldeps", action="store_false",
                      help="check dependencies exactly as given, opposite of --alldeps")
    parser.add_option("--recursive", action="store_true",
                      help="recursively query for packages (for whatrequires)")
    parser.add_option("--whatprovides", action="store_true",
                      help="query what package(s) provide a capability")
    parser.add_option("--whatrequires", action="store_true",
                      help="query what package(s) require a capability")
    parser.add_option("--whatobsoletes", action="store_true",
                      help="query what package(s) obsolete a capability")
    parser.add_option("--whatconflicts", action="store_true",
                      help="query what package(s) conflicts with a capability")
    # group stuff
    parser.add_option("-g", "--group", default=0, action="store_true", 
                      help="query groups instead of packages")
    parser.add_option("--grouppkgs", default="default",
                      help="filter which packages (all,optional etc) are shown from groups")
    # other opts
    parser.add_option("--archlist",
                      help="only query packages of certain architecture(s)")
    parser.add_option("--releasever", default=None,
                      help="set value of $releasever in yum config and repo files")
    parser.add_option("--pkgnarrow", default="repos",
                      help="limit query to installed / available / recent / updates / extras / available + installed / repository (default) packages")
    parser.add_option("--show-duplicates", action="store_true",
                      dest="show_dupes",
                      help="show all versions of packages")
    parser.add_option("--show-dupes", action="store_true",
                      help="show all versions of packages")
    parser.add_option("--repoid", action="append",
                      help="specify repoids to query, can be specified multiple times (default is all enabled)")
    parser.add_option("--enablerepo", action="append", dest="enablerepos",
                      help="specify additional repoids to query, can be specified multiple times")
    parser.add_option("--disablerepo", action="append", dest="disablerepos",
                      help="specify repoids to disable, can be specified multiple times")                      
    parser.add_option("--repofrompath", action="append",
                      help="specify repoid & paths of additional repositories - unique repoid and complete path required, can be specified multiple times. Example. --repofrompath=myrepo,/path/to/repo")
    parser.add_option("--plugins", action="store_true", default=False,
                      help="enable yum plugin support")
    parser.add_option("--quiet", action="store_true", 
                      help="quiet (no output to stderr)", default=True)
    parser.add_option("--verbose", action="store_false",
                      help="verbose output", dest="quiet")
    parser.add_option("-C", "--cache", action="store_true",
                      help="run from cache only")
    parser.add_option("--tempcache", action="store_true",
                      help="use private cache (default when used as non-root)")
    parser.add_option("--querytags", action="store_true",
                      help="list available tags in queryformat queries")
    parser.add_option("-c", "--config", dest="conffile",
                      help="config file location")

    (opts, regexs) = parser.parse_args()

    if opts.querytags:
        querytags.sort()
        for tag in querytags:
            print tag
        sys.exit(0)

    if len(regexs) < 1:
        if opts.all:
            regexs = ['*']
        else:
            print parser.format_help()
            sys.exit(1)

    pkgops = []
    sackops = []
    archlist = None
    if opts.info:
        pkgops.append("info")
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
    if opts.alldeps:
        needfiles = 1
    if opts.envra:
        pkgops.append("envra")
    if opts.nvr:
        pkgops.append("nvr")
    if opts.source:
        pkgops.append("source")
    if opts.srpm:
        needsource = 1
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
        pkgops.append("location")
    if opts.groupmember:
        sackops.append("groupmember")
        needgroup = 1
    if opts.group:
        needgroup = 1

    if opts.nevra or (len(pkgops) == 0 and len(sackops) == 0):
        pkgops.append("queryformat")

    repoq = YumBaseQuery(pkgops, sackops, opts)

    # silence initialisation junk from modules etc unless verbose mode
    initnoise = (not opts.quiet) * 2
    repoq.preconf.releasever = opts.releasever
    if opts.conffile:
        repoq.doConfigSetup(fn=opts.conffile, debuglevel=initnoise, init_plugins=opts.plugins)
    else:
        repoq.doConfigSetup(debuglevel=initnoise, init_plugins=opts.plugins)

    if opts.repofrompath:
        # setup the fake repos
        for repo in opts.repofrompath:
            repoid,repopath = tuple(repo.split(','))
            if repopath[0] == '/':
                baseurl = 'file://' + repopath
            else:
                baseurl = repopath
                
            repoq.add_enable_repo(repoid, baseurls=[baseurl], 
                    basecachedir=repoq.conf.cachedir)
            if not opts.quiet:
                repoq.logger.info( "Added %s repo from %s" % (repoid,repopath))

        
    # Show what is going on, if --quiet is not set.
    if not opts.quiet and sys.stdout.isatty():
        repoq.repos.setProgressBar(TextMeter(fo=sys.stdout))
        repoq.repos.callback = output.CacheProgressCallback()
        yumout = output.YumOutput()
        freport = ( yumout.failureReport, (), {} )
        repoq.repos.setFailureCallback( freport )       
    
    if not repoq.setCacheDir(opts.tempcache):
        repoq.logger.error("Error: Could not make cachedir, exiting")
        sys.exit(50)

    if opts.cache:
        repoq.conf.cache = True
        if not opts.quiet:
            repoq.logger.info('Running from cache, results might be incomplete.')
        

    if opts.show_dupes:
        repoq.conf.showdupesfromrepos = True
            
    if opts.repoid:
        for repo in repoq.repos.findRepos('*'):
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                repo.enable()
    if opts.disablerepos:
        for repo_match in opts.disablerepos:
            for repo in repoq.repos.findRepos(repo_match):
                repo.disable()

    if opts.enablerepos:    
        for repo_match in opts.enablerepos:
            for repo in repoq.repos.findRepos(repo_match):
                repo.enable()

    try:
        repoq.doRepoSetup()
    except yum.Errors.RepoError, e:
        repoq.logger.error("Could not setup repo: %s" % (e))
        sys.exit(50)
    
    for exp in regexs:
        if exp.endswith('.src'):
            needsource = 1
            break

    if opts.archlist:
        archlist = opts.archlist.split(',')
    elif needsource:
        archlist = getArchList()
        archlist.append('src')

    try:
        repoq.doSackSetup(archlist=archlist)
        repoq.doTsSetup()
        if needfiles:
            repoq.repos.populateSack(mdtype='filelists')
        if needother:
            repoq.repos.populateSack(mdtype='otherdata')
        if needgroup:
            repoq.doGroupSetup()
    except (yum.Errors.RepoError, yum.Errors.GroupsError), e:
        repoq.logger.error(e)
        sys.exit(1)

    repoq.runQuery(regexs)

if __name__ == "__main__":
    misc.setup_locale()
    main(sys.argv)
                
# vim:sw=4:sts=4:expandtab              

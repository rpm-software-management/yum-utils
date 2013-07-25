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
# (c) pmatilai@laiskiainen.org


import sys
sys.path.insert(0, '/usr/share/yum-cli')

import signal
import re
import fnmatch
import time
import os
import os.path
import urlparse

from optparse import OptionParser
from optparse import SUPPRESS_HELP

import logging
import yum
import yum.misc as misc
import yum.config
import yum.Errors
import yum.packages
from yum.i18n import to_unicode
from rpmUtils.arch import getArchList, getBaseArch
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
Source      : %{sourcerpm}
Description :\n%{description}""",
}

querytags = [ 'name', 'version', 'release', 'epoch', 'arch', 'summary',
              'description', 'packager', 'url', 'buildhost', 'sourcerpm',
              'vendor', 'group', 'license', 'buildtime', 'filetime',
              'installedsize', 'archivesize', 'packagesize', 'repoid', 
              'requires', 'provides', 'conflicts', 'obsoletes',
              'relativepath', 'hdrstart', 'hdrend', 'id',
              'checksum', 'pkgid', 'committer', 'committime',
              'ui_evr', 'evr', 'ui_nevra', 'ui_envra',
              'ui_from_repo', 'base_package_name', 'size', 'xattr_origin_url',
              'ui_evra', 'ui_nevr', 'na', 'vr', 'vra', 'evr', 'evra',
              'nvr', 'nvra', 'nevr', 'nevra', 'envr', 'envra',

              'repo.<attr of the repo object>',
              'yumdb.<attr of the yumdb object>',
              '<attr of the yum object>'
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

class queryError(Exception):
    def __init__(self, value=None):
        Exception.__init__(self)
        self.value = value
    def __str__(self):
        return "%s" %(self.value,)

    def __unicode__(self):
        return '%s' % to_unicode(self.value)
        

class DotPlot(object):
    def __init__(self):

        print 'digraph packages {',
        print """
size="20.69,25.52";
ratio="fill";
rankdir="TB";
orientation=port;
node[style="filled"];
outputorder="edgesfirst";
ranksep="1";
"""
    
    def addPackage(self, pkg, deps):
        # color calculations lifted from rpmgraph 
        h=0.5+(0.6/23*len(deps))
        s=h+0.1
        b=1.0
        
        print '"%s" [color="%s %s %s"];' % (pkg, h, s, b)
        print '"%s" -> {' % pkg
        for req in deps:
            print '"%s"' % req
        print '} [color="%s %s %s"];\n' % (h, s, b)
    
    def __del__(self):
        print "}"

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

    def __init__(self, pkg, qf, yb=None):
        self.yb = yb
        self.pkg = pkg
        self.qf = qf
        self.name = pkg.name
        self.classname = None
        self._translated_qf = {}
    
    def __getitem__(self, item):
        item = item.lower()
        if hasattr(self, "fmt_%s" % item):
            return getattr(self, "fmt_%s" % item)()
        elif item.startswith('repo.'):
            repo_item = item.split('.')[1]
            try:
                return getattr(self.pkg.repo, repo_item)
            except AttributeError,e:
                raise queryError("Invalid repo querytag '%s' for %s: %s" % (repo_item, self.classname, self.pkg))
        elif hasattr(self.pkg, item):
            return getattr(self.pkg, item)

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
        except (KeyError, ValueError):
            if item == "license":
                res = ", ".join(self.pkg.licenses)
            else:
                raise queryError("Invalid querytag '%s' for %s: %s" % (item, self.classname, self.pkg))

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

    def fmt_queryformat(self, **kw):

        if not self.qf:
            return self.fmt_nevra()

        # Override .qf for fun and profit...
        if self.qf not in self._translated_qf:
            qf = self.qf

            qf = qf.replace("\\n", "\n")
            qf = qf.replace("\\t", "\t")
            pattern = re.compile('%([-\d]*?){([:\.\w]*?)}')
            fmt = re.sub(pattern, r'%(\2)\1s', qf)
            self._translated_qf[self.qf] = fmt
        return self._translated_qf[self.qf] % self

    def fmt_requires(self, **kw):
        if self.yb.options.output in ("ascii-tree", "dot-tree"):
            self.fmt_tree_requires(output = self.yb.options.output,
                                tree_level = self.yb.options.tree_level,
                                dot = self.yb.options.dot)
        else:
            return "\n".join(self.prco('requires'))

    def fmt_provides(self, **kw):
        return "\n".join(self.prco('provides'))

    def fmt_conflicts(self, **kw):
        if self.yb.options.output in ("ascii-tree", "dot-tree"):
            self.fmt_tree_conflicts(output = self.yb.options.output,
                                tree_level = self.yb.options.tree_level,
                                dot = self.yb.options.dot)
        else:
            return "\n".join(self.prco('conflicts'))

    def fmt_obsoletes(self, **kw):
        if self.yb.options.output in ("ascii-tree", "dot-tree"):
            self.fmt_tree_obsoletes(output = self.yb.options.output,
                                tree_level = self.yb.options.tree_level,
                                dot = self.yb.options.dot)
        else:
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

    def tree_print_req(self, req, val, level):
        indent = ''
        if level:
            indent = ' |  ' * (level - 1) + ' \_  '
        print "%s%s [%s]" % (indent, str(req), str(val))

    # These are common helpers for the --tree-* options...
    def _tree_print_req(self, req, val, level):
        indent = ''
        if level:
            indent = ' |  ' * (level - 1) + ' \_  '
        self.pkg = req
        self.name = req.name
        print "%s%s [%s]" % (indent, self.fmt_queryformat(), str(val))
    def _tree_pkg2uniq(self, pkg):
        """ Turn a pkg into a "unique" req."""
        if self.yb and self.yb.conf.showdupesfromrepos:
            return str(pkg)
        return "%s.%s" % (pkg.name, getBaseArch(pkg.arch))
    def _tree_pkg2val(self, reqs, pkg):
        reqs = sorted(reqs[self._tree_pkg2uniq(pkg)])
        return str(len(reqs)) + ": " + ", ".join(reqs)
    def _tree_maybe_add_pkg(self, all_reqs, loc_reqs, pkgs, pkg, val):
        req = self._tree_pkg2uniq(pkg)
        if req in loc_reqs:
            loc_reqs[req].add(val)
            return
        if req in all_reqs:
            pkgs[pkg]     = None
            loc_reqs[req] = set([val])
            return
        pkgs[pkg]     = True
        loc_reqs[req] = set([val])
        all_reqs[req] = True
    def _tree_maybe_add_pkgs(self, all_reqs, tups, tup2pkgs):
        rpkgs    = {}
        loc_reqs = {}
        for rptup in tups:
            (rpn, rpf, (rp,rpv,rpr)) = rptup
            if rpn.startswith('rpmlib'):
                continue

            rname = yum.misc.prco_tuple_to_string(rptup)
            for npkg in sorted(tup2pkgs(rptup, rname), reverse=True):
                self._tree_maybe_add_pkg(all_reqs, loc_reqs, rpkgs, npkg, rname)
        return rpkgs, loc_reqs
    def _fmt_tree_prov(self, prco_type, **kw):
        pkg      = kw.get('pkg', self.pkg)
        req      = kw.get('req', 'cmd line')
        level    = kw.get('level', 0)
        all_reqs = kw.get('all_reqs', {})
        
        if kw['output'].lower() == 'dot-tree':
            if 'dot' not in kw.keys() or kw['dot'] is None:
                kw['dot'] = DotPlot()
        elif 'dot' not in kw.keys() or kw['dot'] is None:
            kw['dot'] = None
        dot      = kw['dot']
        
        if str(kw['tree_level']).lower() != 'all':
            try: 
                kw['tree_level'] = int(kw['tree_level'])
            except ValueError, er:
                kw['tree_level'] = 'all'
        
        if not 'output' in kw.keys():
            kw['output'] = 'ascii-tree'

        #  Level means something a bit different for dot, because we have to
        # lookup it's packages ... but we don't for ascii. *sigh*
        if dot is None:
            self._tree_print_req(pkg, req, level)
            lim = level + 1
            if str(kw['tree_level']).lower() != 'all' and \
                int(kw['tree_level']) < int(lim):
                return

        __req2pkgs = {}
        def req2pkgs(ignore, req):
            req = str(req)
            if req in __req2pkgs:
                return __req2pkgs[req]

            if self.yb is None:
                return []
            yb = self.yb

            providers = []
            try:
                # XXX rhbz#246519, for some reason returnPackagesByDep() fails
                # to find some root level directories while 
                # searchPackageProvides() does... use that for now
                matches = self.yb.searchPackageProvides([req])
                if self.yb.options.pkgnarrow == 'repos':
                    # Sucks that we do the work, and throw it away...
                    for provider in matches:
                        if provider.repoid != 'installed':
                            providers.append(provider)
                elif self.yb.options.pkgnarrow == 'installed':
                    # Sucks that we do the work, and throw it away...
                    for provider in matches:
                        if provider.repoid == 'installed':
                            providers.append(provider)
                else:
                    # Assume "all"
                    providers = matches.keys()


            except yum.Errors.RepoError:
                raise
            except yum.Errors.YumBaseError, err:
                print >>sys.stderr, "No package provides %s" % req
                return []

            __req2pkgs[req] = providers
            return providers 
        
        tups = getattr(pkg, prco_type)
        rpkgs, loc_reqs = self._tree_maybe_add_pkgs(all_reqs, tups, req2pkgs)
        if dot is not None:
            dot.addPackage(pkg, rpkgs)
            lim = level + 2
        nlevel = level + 1
        if str(kw['tree_level']).lower() != 'all' and \
            int(kw['tree_level']) < int(lim):
            return
        for rpkg in sorted(rpkgs):
            if pkg.verEQ(rpkg):
                continue
            if rpkgs[rpkg] is None:
                req = self._tree_pkg2val(loc_reqs, rpkg)
                if dot is None:
                    self._tree_print_req(rpkg, req, nlevel)
                continue
            self._fmt_tree_prov(prco_type,
                                pkg = rpkg, level = nlevel, all_reqs = all_reqs,
                                req = self._tree_pkg2val(loc_reqs, rpkg),
                                tree_level = kw['tree_level'],
                                output = kw['output'],
                                dot = dot)
        
    def fmt_tree_requires(self, **kw):
        return self._fmt_tree_prov('requires', **kw)
    def fmt_tree_conflicts(self, **kw):
        return self._fmt_tree_prov('conflicts', **kw)

    def fmt_tree_obsoletes(self, **kw):
        pkg      = kw.get('pkg', self.pkg)
        req      = kw.get('req', 'cmd line')
        level    = kw.get('level', 0)
        all_reqs = kw.get('all_reqs', {})
        
        if kw['output'].lower() == 'dot-tree':
            if 'dot' not in kw.keys() or kw['dot'] is None:
                kw['dot'] = DotPlot()
        elif 'dot' not in kw.keys() or kw['dot'] is None:
            kw['dot'] = None
        dot      = kw['dot']
        
        if str(kw['tree_level']).lower() != 'all':
            try: 
                kw['tree_level'] = int(kw['tree_level'])
            except ValueError, er:
                kw['tree_level'] = 'all'
        
        if not 'output' in kw.keys():
            kw['output'] = 'ascii-tree'
        
        #  Level means something a bit different for dot, because we have to
        # lookup it's packages ... but we don't for ascii. *sigh*
        if dot is None:
            self._tree_print_req(pkg, req, level)
            lim = level + 1
            if str(kw['tree_level']).lower() != 'all' and \
                int(kw['tree_level']) < int(lim):
                return

        def obs2pkgs():
            if self.yb is None:
                return []
            yb = self.yb

            obss = []
            if self.yb.options.pkgnarrow in ('all', 'repos'):
                for obs_n in pkg.obsoletes_names:
                    for opkg in yb.pkgSack.searchNevra(name=obs_n):
                        if opkg.obsoletedBy([pkg]):
                            obss.append(opkg)
            if self.yb.options.pkgnarrow in ('all', 'installed'):
                skip = set([opkg.pkgtup for opkg in obss])
                for obs_n in pkg.obsoletes_names:
                    for opkg in yb.rpmdb.searchNevra(name=obs_n):
                        if opkg.pkgtup in skip:
                            continue
                        if opkg.obsoletedBy([pkg]):
                            obss.append(opkg)

            return obss

        dot = kw['dot']
        
        if level:
            reason = ''
        else:
            reason = 'cmd line'
        rpkgs = obs2pkgs()
        if dot is not None:
            dot.addPackage(pkg, rpkgs)
            lim = level + 2
        all_reqs[pkg] = None
        nlevel = level + 1
        if str(kw['tree_level']).lower() != 'all' and \
            int(kw['tree_level']) < int(lim):
            return
        for rpkg in sorted(rpkgs):
            if pkg.verEQ(rpkg):
                continue
            if rpkg in all_reqs and dot is None:
                self._tree_print_req(rpkg, '', nlevel)
                continue
            self.fmt_tree_obsoletes(pkg=rpkg, level=nlevel, all_reqs=all_reqs,
                                    req = pkg.name,
                                    tree_level = kw['tree_level'],
                                    output = kw['output'],
                                    dot = dot)

    def fmt_tree_what_requires(self, **kw):
        pkg      = kw.get('pkg', self.pkg)
        req      = kw.get('req', 'cmd line')
        level    = kw.get('level', 0)
        all_reqs = kw.get('all_reqs', {})
        
        if kw['output'].lower() == 'dot-tree':
            if 'dot' not in kw.keys() or kw['dot'] is None:
                kw['dot'] = DotPlot()
        dot      = kw['dot']

        if str(kw['tree_level']).lower() != 'all':
            try: 
                kw['tree_level'] = int(kw['tree_level'])
            except ValueError, er:
                kw['tree_level'] = 'all'
        
        if not 'output' in kw.keys():
            kw['output'] = 'ascii-tree'

        #  Level means something a bit different for dot, because we have to
        # lookup it's packages ... but we don't for ascii. *sigh*
        if dot is None:
            self._tree_print_req(pkg, req, level)
            lim = level + 1
            if str(kw['tree_level']).lower() != 'all' and \
                int(kw['tree_level']) < int(lim):
                return

        __prov2pkgs = {}
        def prov2pkgs(prov, ignore):
            if str(prov) in __prov2pkgs:
                return __prov2pkgs[str(prov)]

            if self.yb is None:
                return []
            yb = self.yb

            arequirers = []
            irequirers = []
            try:
                skip = {}
                if yb.options.pkgnarrow in ('all', 'installed'):
                    irequirers = yb.rpmdb.getRequires(prov[0],prov[1],prov[2])
                    irequirers = irequirers.keys()
                if yb.options.pkgnarrow in ('all', 'repos'):
                    areqs = yb.pkgSack.getRequires(prov[0],prov[1],prov[2])
                    if not irequirers:
                        arequirers = areqs.keys()
                    else:
                        skip = set([pkg.pkgtup for pkg in irequirers])
                        arequirers = [pkg for pkg in areqs
                                      if pkg.pkgtup not in skip]

            except yum.Errors.RepoError:
                raise
            except yum.Errors.YumBaseError, err:
                print >>sys.stderr, "No package provides %s" % str(prov)
                return []

            __prov2pkgs[str(prov)] = arequirers + irequirers
            return arequirers + irequirers

        filetupes = []
        for n in pkg.filelist + pkg.dirlist + pkg.ghostlist:
            filetupes.append((n, None, (None, None, None)))
        
        tups = pkg.provides + filetupes
        rpkgs, loc_reqs = self._tree_maybe_add_pkgs(all_reqs, tups, prov2pkgs)
        
        if dot is not None:
            dot.addPackage(pkg, rpkgs)
            lim = level + 2
        nlevel = level + 1
        
        if str(kw['tree_level']).lower() != 'all' and \
            int(kw['tree_level']) < int(lim):
            return
        for rpkg in sorted(rpkgs):
            if pkg.verEQ(rpkg): # Remove deps. on self.
                continue
            if rpkgs[rpkg] is None:
                req = self._tree_pkg2val(loc_reqs, rpkg)
                if dot is None:
                    self._tree_print_req(rpkg, req, nlevel)
                continue
            self.fmt_tree_what_requires(pkg=rpkg,
                                        level=nlevel, all_reqs=all_reqs,
                                        req=self._tree_pkg2val(loc_reqs, rpkg),
                                        tree_level = kw['tree_level'],
                                        output = kw['output'],
                                        dot = dot)


class repoPkgQuery(pkgQuery):
    """
    I wrap a query of a non-installed package available in the repository.
    """
    def __init__(self, pkg, qf, yb=None):
        pkgQuery.__init__(self, pkg, qf, yb)
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

    def __init__(self, pkg, qf, yb=None):
        pkgQuery.__init__(self, pkg, qf, yb)
        self.classname = 'installed pkg'

    def __getitem__(self, item):
        if item in self.tagmap:
            return self.pkg.tagByName(self.tagmap[item])
        elif item.startswith('yumdb_info.'):
            yumdb_item = item.split('.')[1]
            try:
                return getattr(self.pkg.yumdb_info, yumdb_item)
            except AttributeError,e:
                raise queryError("Invalid yumdb querytag '%s' for %s: %s" % (yumdb_item, self.classname, self.pkg))
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
                author = to_unicode(author)
                message = to_unicode(message)
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
    def fmt_queryformat(self, **kw):
        return self.fmt_nevra()

    def fmt_nevra(self, **kw):
        return ["%s - %s" % (self.id, self.name)]

    def fmt_list(self, **kw):
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
        
    def fmt_requires(self, **kw):
        return self.group.mandatory_packages

    def fmt_info(self, **kw):
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
        self._sacks = []
        if self.options.pkgnarrow in ('all', 'extras', 'installed'):
            self._sacks.append('rpmdb')
        if self.options.pkgnarrow not in ('extras', 'installed'):
            self._sacks.append('pkgSack')

    def queryPkgFactory(self, pkgs, plain_pkgs=False):
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

            if plain_pkgs:
                qpkgs.append(pkg)
                continue

            if isinstance(pkg, yum.packages.YumInstalledPackage):
                qpkg = instPkgQuery(pkg, qf, self)
            else:
                qpkg = repoPkgQuery(pkg, qf, self)
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
        if 'patterns' in kwargs:
            if len(kwargs['patterns']) == 1 and kwargs['patterns'][0] == '*':
                kwargs['patterns'] = None

        if self.options.pkgnarrow == "repos":
            # self.pkgSack is a yum.packageSack.MetaSack
            if self.conf.showdupesfromrepos:
                pkgs = self.pkgSack.returnPackages(**kwargs)
            else:
                try:
                    pkgs = self.pkgSack.returnNewestByNameArch(**kwargs)
                except yum.Errors.PackageSackError:
                    pkgs = []
                except yum.Errors.RepoError, e:
                    raise queryError(e)
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
        except yum.Errors.RepoError:
            raise
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
                    
    def matchPkgs(self, items, plain_pkgs=False):
        pkgs = self.returnPkgList(patterns=items)
        return self.queryPkgFactory(pkgs, plain_pkgs)

    def matchSrcPkgs(self, items):
        srpms = []
        for name in items:
            for pkg in self.returnByName(name):
                if pkg.isSource(): 
                    continue
                src = pkg["sourcerpm"][:-4]
                srpms.extend(self.returnByName(src))
        return srpms
    
    def yum_search(self, terms):
        """use yum's search generator to search arbitrary fields"""
        
        pkgs = []
        fields = self.options.searchfields
        if not fields:
            fields = ['name', 'summary']
        try:
            matching = self.searchGenerator(fields, terms, searchtags=False)
        
            for (po, matched_value) in matching:
                if isinstance(po, yum.packages.YumInstalledPackage):
                    if self.options.pkgnarrow not in ('all', 'installed', 'extras'):
                        continue
                if isinstance(po, yum.sqlitesack.YumAvailablePackageSqlite):
                    if self.options.pkgnarrow not in ('all', 'available', 'repos'):
                        continue
                pkgs.append(po)

        except (yum.Errors.RepoError,ValueError), e:
            raise queryError("Could not run search: %s" % e)
        
        return self.queryPkgFactory(pkgs)
        
    def _at_grps(self, items):
        #  We want to move from @foo => lists of package names here, to make
        # a bunch of things easier. Ie. pkgs. ops. on lists of packages from
        # groups.
        nitems = []
        for item in items:
            if item and item[0] == '@':
                for grp in self.matchGroups([item[1:]]):
                    nitems.extend(grp.group.packages)
                # Give warning when no matches?
                continue
            nitems.append(item)
        return nitems

    def runQuery(self, items):
        plain_pkgs = False
        if self.options.group:
            pkgs = self.matchGroups(items)
        elif self.options.groupmember:
            pkglist = self.matchPkgs(items, plain_pkgs=True)
            for pkg in sorted(pkglist):
                print to_unicode(pkg)
                for group in sorted(self.find_groupmember(pkg.name)):
                    print to_unicode('  @%s' % group)
            pkgs = []
        elif self.options.search:
            plain_pkgs = False
            pkgs = []
            try:
                pkgs = self.yum_search(items)
            except queryError, e:
                self.logger.error(e)
        else:
            items = self._at_grps(items)
            if self.options.srpm:
                pkgs = self.matchSrcPkgs(items)

            else:
                pkgs = []
                if not self.sackops:
                    plain_pkgs = True
                    try:
                        pkgs = self.matchPkgs(items, plain_pkgs=plain_pkgs)
                    except yum.Errors.RepoError, e:
                        raise queryError("Could not match packages: %s" % to_unicode(e))
                for prco in items:
                    for oper in self.sackops:
                        try:
                            for p in self.doQuery(oper, prco): 
                                if p:
                                    pkgs.append(p)
                        except queryError, e:
                            self.logger.error(e)

        if plain_pkgs:
            iq = None
            rq = None
            qf = self.options.queryformat or std_qf["nevra"]
            pkgs = sorted(pkgs)
        for pkg in pkgs:
            if plain_pkgs:
                if isinstance(pkg, yum.packages.YumInstalledPackage):
                    if iq is None:
                        iq = instPkgQuery(pkg, qf, self)
                    iq.pkg = pkg
                    iq.name = pkg.name
                    pkg = iq
                else:
                    if rq is None:
                        rq = repoPkgQuery(pkg, qf, self)
                    rq.pkg = pkg
                    rq.name = pkg.name
                    pkg = rq
            if not self.pkgops:
                print to_unicode(pkg)
            for oper in self.pkgops:
                try:
                    out = pkg.doQuery(oper, 
                        tree_level = self.options.tree_level,
                        output = self.options.output,
                        dot = self.options.dot)
                    if out:
                        print to_unicode(out)
                except queryError, e:
                    self.logger.error(e)

    def doQuery(self, method, *args, **kw):
        return getattr(self, "fmt_%s" % method)(*args, **kw)

    def find_groupmember(self, name, **kw):
        grps = []
        for group in self.comps.get_groups():
            if name in group.packages:
                grps.append(group.groupid)
        return grps

    def fmt_whatprovides(self, name, **kw):
        return self.returnPackagesByDepStr(name)

    def fmt_whatrequires(self, name, **kw):
        pkgs = {}
        done = set() # keep track of names we have already visited

        def require_recursive(name):
            if name in done:
                return
            done.add(name)

            provs = [name]
                    
            if self.options.alldeps:
                for pkg in self.returnByName(name):
                    provs.extend(pkg.prco("provides"))
                    provs.extend(pkg.files())

            for prov in provs:
                for sackstr in self._sacks:
                    sack = getattr(self, sackstr)
                    for pkg in sack.searchRequires(prov):
                        pkgs[pkg.pkgtup] = pkg
                        if self.options.recursive:
                            require_recursive(pkg.name)
                

        
        if self.options.output not in ('ascii-tree','dot-tree'):
            require_recursive(name)
        return self.queryPkgFactory(sorted(pkgs.values()))

    def fmt_whatobsoletes(self, name, **kw):
        pkgs = []
        for sackstr in self._sacks:
            sack = getattr(self, sackstr)
            for pkg in sack.searchObsoletes(name):
                pkgs.append(pkg)
        return self.queryPkgFactory(pkgs)
            
    def fmt_whatconflicts(self, name, **kw):
        pkgs = []
        for sackstr in self._sacks:
            sack = getattr(self, sackstr)
            for pkg in sack.searchConflicts(name):
                pkgs.append(pkg)
        return self.queryPkgFactory(pkgs)

    def fmt_requires(self, name, **kw):
        pkgs = {}
        done = set()
        def require_recursive(pkg):
            if pkg.name in done:
                return
            done.add(pkg.name)

            for req in pkg.prco("requires"):
                for res in self.fmt_whatprovides(req):
                    pkgs[(res.name, res.pkg.arch)] = res
                    if self.options.recursive:
                        require_recursive(res)

        for pkg in self.returnByName(name):
            require_recursive(pkg)

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

    def _parseSetOpts(self, setopts):
        """parse the setopts list handed to us and saves the results as
           repo_setopts and main_setopts in the yumbase object"""

        repoopts = {}
        mainopts = yum.misc.GenericHolder()
        mainopts.items = []

        bad_setopt_tm = []
        bad_setopt_ne = []

        for item in setopts:
            vals = item.split('=')
            if len(vals) > 2:
                bad_setopt_tm.append(item)
                continue
            if len(vals) < 2:
                bad_setopt_ne.append(item)
                continue
            k,v = vals
            period = k.find('.')
            if period != -1:
                repo = k[:period]
                k = k[period+1:]
                if repo not in repoopts:
                    repoopts[repo] = yum.misc.GenericHolder()
                    repoopts[repo].items = []
                setattr(repoopts[repo], k, v)
                repoopts[repo].items.append(k)
            else:
                setattr(mainopts, k, v)
                mainopts.items.append(k)

        self.main_setopts = mainopts
        self.repo_setopts = repoopts

        return bad_setopt_tm, bad_setopt_ne


def main(args):

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
                      help="limit query to installed / available / recent / updates / extras / all (available + installed) / repository (default) packages")
    parser.add_option("--installed", action="store_true", default=False,
                      help="limit query to installed pkgs only")
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
    parser.add_option("--plugins", action="store_true", default=False,
                      help="enable yum plugin support")
    parser.add_option("--quiet", action="store_true", 
                      help="quiet output, only error output to stderr (default enabled)", default=True)
    parser.add_option("--verbose", action="store_false",
                      help="verbose output (opposite of quiet)", dest="quiet")
    parser.add_option("-C", "--cache", action="store_true",
                      help="run from cache only")
    parser.add_option("--tempcache", action="store_true",
                      help="use private cache (default when used as non-root)")
    parser.add_option("--querytags", action="store_true",
                      help="list available tags in queryformat queries")
    parser.add_option("-c", "--config", dest="conffile",
                      help="config file location")
    parser.add_option("--tree-requires", action="store_true",
                      dest="tree_requires",
                      help=SUPPRESS_HELP)
    parser.add_option("--tree-conflicts", action="store_true",
                      dest="tree_conflicts",
                      help=SUPPRESS_HELP)
    parser.add_option("--tree-obsoletes", action="store_true",
                      dest="tree_obsoletes",
                      help=SUPPRESS_HELP)
    parser.add_option("--tree-whatrequires", action="store_true",
                      dest="tree_what_requires",
                      help=SUPPRESS_HELP)
    parser.add_option("--level", dest="tree_level", default="all",
                      help="levels to display (can be any number or 'all', default to 'all')")
    parser.add_option("--output", dest="output", default="text",
                      help="output format to use (can be text|ascii-tree|dot-tree, default to 'text')")
    parser.add_option("--search", action="store_true",
                      dest="search", default=False,
                      help="Use yum's search to return pkgs")
    parser.add_option("--search-fields", action="append", dest="searchfields",
                      default=[],
                      help="search fields to search using --search")
    parser.add_option("", "--setopt", dest="setopts", default=[],
                     action="append",
                     help="set arbitrary config and repo options")
                      

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
        pkgops.append("list")
    if opts.envra:
        pkgops.append("envra")
    if opts.nvr:
        pkgops.append("nvr")
    if opts.source:
        pkgops.append("source")
    if opts.tree_requires:
        opts.output = "ascii-tree"
        pkgops.append("tree_requires")
    if opts.tree_conflicts:
        opts.output = "ascii-tree"
        pkgops.append("tree_conflicts")
    if opts.tree_obsoletes:
        opts.output = "ascii-tree"
        pkgops.append("tree_obsoletes")
    if opts.tree_what_requires:
        opts.output = "ascii-tree"
        pkgops.append("tree_what_requires")
    if opts.output == "dot-tree":
        opts.dot = DotPlot()
    else:
        opts.dot = None
    if opts.srpm:
        needsource = 1
    if opts.whatrequires:
        if opts.output != 'text':
            pkgops.append("tree_what_requires")
        else:
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
        needgroup = 1
    if opts.group:
        needgroup = 1
    if opts.installed:
        opts.pkgnarrow = 'installed'

    if opts.nevra:
        pkgops.append("nevra")
    elif len(pkgops) == 0 and len(sackops) == 0:
        pkgops.append("queryformat")

    for exp in regexs:
        if exp.endswith('.src'):
            needsource = 1
            break

    if opts.archlist:
        archlist = opts.archlist.split(',')
    elif needsource:
        archlist = getArchList()
        archlist.append('src')

    if opts.searchfields:
        opts.search = True
        
    repoq = YumBaseQuery(pkgops, sackops, opts)

    # go through all the setopts and set the global ones
    bad_setopt_tm, bad_setopt_ne = repoq._parseSetOpts(opts.setopts)

    if repoq.main_setopts:
        for opt in repoq.main_setopts.items:
            setattr(opts, opt, getattr(repoq.main_setopts, opt))

    # silence initialisation junk from modules etc unless verbose mode
    initnoise = (not opts.quiet) * 2
    repoq.preconf.releasever = opts.releasever
    if archlist and not archlist[0] == 'src':
        repoq.preconf.arch = archlist[0]
    if opts.conffile is not None:
        repoq.preconf.fn = opts.conffile
    repoq.preconf.debuglevel = initnoise
    repoq.preconf.init_plugins = opts.plugins
    repoq.conf

    for item in  bad_setopt_tm:
        msg = "Setopt argument has multiple values: %s"
        repoq.logger.warning(msg % item)
    for item in  bad_setopt_ne:
        msg = "Setopt argument has no value: %s"
        repoq.logger.warning(msg % item)
    # now set  all the non-first-start opts from main from our setopts
    if repoq.main_setopts:
        for opt in repoq.main_setopts.items:
            if not hasattr(repoq.conf, opt):
                msg ="Main config did not have a %s attr. before setopt"
                repoq.logger.warning(msg % opt)
            setattr(repoq.conf, opt, getattr(repoq.main_setopts, opt))

    if opts.repofrompath:
        # setup the fake repos
        for repo in opts.repofrompath:
            tmp = tuple(repo.split(','))
            if len(tmp) != 2:
                repoq.logger.error("Error: Bad repofrompath argument: %s" %repo)
                continue
            repoid,repopath = tmp
            if repopath[0] == '/':
                baseurl = 'file://' + repopath
            else:
                baseurl = repopath
                
            try:
                repoq.add_enable_repo(repoid, baseurls=[baseurl],
                                      basecachedir=repoq.conf.cachedir,
                                      timestamp_check=False)
            except yum.Errors.DuplicateRepoError, e:
                repoq.logger.error(e)
                sys.exit(1)
            if not opts.quiet:
                repoq.logger.info( "Added %s repo from %s" % (repoid,repopath))

        
    # Show what is going on, if --quiet is not set.
    if not opts.quiet and sys.stdout.isatty():
        yumout = output.YumOutput()
        freport = ( yumout.failureReport, (), {} )
        if hasattr(repoq, 'prerepoconf'):
            repoq.prerepoconf.progressbar = TextMeter(fo=sys.stdout)
            repoq.prerepoconf.callback = output.CacheProgressCallback()
            repoq.prerepoconf.failure_callback = freport
        else:
            repoq.repos.setProgressBar(TextMeter(fo=sys.stdout))
            repoq.repos.callback = output.CacheProgressCallback()
            repoq.repos.setFailureCallback(freport)
    
    if not repoq.setCacheDir(opts.tempcache):
        repoq.logger.error("Error: Could not make cachedir, exiting")
        sys.exit(50)

    if opts.cache:
        repoq.conf.cache = True
        if not opts.quiet:
            repoq.logger.info('Running from cache, results might be incomplete.')
        

    if opts.show_dupes:
        repoq.conf.showdupesfromrepos = True
            

    if opts.pkgnarrow == 'installed':
        # Just use a blunt hammer here, to make everyone sane:
        opts.repoid = []
        opts.disablerepos = ['*']
        opts.enablerepos  = []

    if opts.repoid:
        found_repos = set()
        for repo in repoq.repos.findRepos('*'):
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                found_repos.add(repo.id)
                repo.enable()
        for not_found in set(opts.repoid).difference(found_repos):
            repoq.logger.error('Repoid %s was not found.' % not_found)

    if opts.disablerepos:
        for repo_match in opts.disablerepos:
            for repo in repoq.repos.findRepos(repo_match):
                repo.disable()

    if opts.enablerepos:    
        for repo_match in opts.enablerepos:
            for repo in repoq.repos.findRepos(repo_match):
                repo.enable()

    while True:
        try: repoq.doLock(); break
        except yum.Errors.LockError, e: pass
        repoq.logger.error(e)
        time.sleep(2)

    try:
        if not hasattr(repoq, 'arch'):
            repoq.doSackSetup(archlist=archlist)
        elif archlist is not None:
            repoq.arch.archlist = archlist

        #  Don't do needfiles, because yum will do it automatically and it's
        # not trivial to get it "right" so we don't download them when not
        # needed.
        if needother:
            repoq.repos.populateSack(mdtype='otherdata')
        if needgroup:
            repoq.doGroupSetup()
    except (yum.Errors.RepoError, yum.Errors.GroupsError), e:
        repoq.logger.error(e)
        sys.exit(1)

    try:
        repoq.runQuery(regexs)
    except yum.Errors.RepoError, e:
        repoq.logger.error(e)
        sys.exit(1)
    except queryError, e:
        repoq.logger.error(e)
        sys.exit(1)

if __name__ == "__main__":
    misc.setup_locale()
    main(sys.argv)
                
# vim:sw=4:sts=4:expandtab              

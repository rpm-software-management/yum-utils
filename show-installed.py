#!/usr/bin/python

"""
TODO:
 * repository descriptions in kickstart format for non default repos
"""

import yum
from optparse import OptionParser
import sys

__stateprefixes = {
    None : '# ',
    "mandatory" : ".",
    "default" : "@",
    "all" : "*"
    }

def state2str(o):
    if isinstance(o, Group):
        o = o.state
    return __stateprefixes[o]

class Group:
    """Additional information about a comps group"""
    def __init__(self, compsgroup, yum, state=None):
        self.id = compsgroup.groupid
        self.state = None
        self.compsgroup = compsgroup
        self.yum = yum

        self.packages = {}
        for n in (None, "mandatory", "default", "all"):
            self.packages[n] = {}
            for s in ("add", "exclude", "exclude_missing", "optional"):
                self.packages[n][s] = set()

    @property
    def add(self):
        """Packages that this group adds to the install"""
        return self.packages[self.state]["add"]

    @property
    def exclude(self):
        """Packages excludes from this group to match the pkg list"""
        return self.packages[self.state]["exclude"]

    @property
    def excludeMissing(self):
        """Excludes that don't have a matching pgk in the repository"""
        return self.packages[self.state]["exclude_missing"]

    @property
    def optional(self):
        """Packages in this group that are not added in the current state"""
        return self.packages[self.state]["optional"]

    @property
    def addons(self):
        """Optional packages that are not added by the group in the given state but nevertheless need to be installed"""
        return self.packages[self.state]["addons"]

    def _buildSets(self, leafpkgs, allpkgs):
        # handle conditionals
        self.conditionals = set()
        for name, dep in self.compsgroup.conditional_packages.iteritems():
            if dep in allpkgs:
                self.conditionals.add(name)

        pkgs = self.conditionals.copy()
        for name, additionalpkgs in (
            ("mandatory", self.compsgroup.mandatory_packages),
            ("default", self.compsgroup.default_packages),
            ("all", self.compsgroup.optional_packages)):
            pkgs.update(additionalpkgs)
            self.__checkGroup(name, pkgs, leafpkgs, allpkgs)

        self.__checkGroup(None, set(), leafpkgs, allpkgs)
        for name, d in self.packages.iteritems():
            d["others"] = pkgs - d["add"] - d["exclude"]
            d["addons"] = d["others"] & leafpkgs

    def __checkGroup(self, name, pkgs, leafpkgs, allpkgs):
        self.packages[name]["add"] = leafpkgs & pkgs
        self.packages[name]["exclude"] = pkgs - allpkgs
        self.packages[name]["exclude_missing"] = set(
            pkg for pkg in self.packages[name]["exclude"] if not self.yum.pkgSack.searchNames([pkg]))
        return

    def _autodetectState(self, allowexcludes, allowed=("default",), sharedpkgs=None):
        """Set state of the group according to the installed packages"""
        win = None
        state = self.state
        for name, d in self.packages.iteritems():
            if name not in allowed and name is not None:
                continue
            if not allowexcludes and d["exclude"]:
                continue
            newshared = set()
            if sharedpkgs:
                for pkg in d["add"]:
                    if pkg in sharedpkgs and len(sharedpkgs[pkg]) > 1:
                        newshared.add(pkg)
            newwin = len(d["add"]) - len(d["exclude"]) - len(newshared) - 1
            if win is None or newwin > win:
                state = name
                win = newwin

        if win <= 0:
            state = None
        # reflect changes in sharedpkgs
        if state != self.state and sharedpkgs is not None:
            for pkg in self.packages[self.state]["add"] - self.packages[state]["add"]:
                if pkg in sharedpkgs:
                    sharedpkgs[pkg].discard(self)
            for pkg in self.packages[state]["add"] - self.packages[self.state]["add"]:
                sharedpkgs.setdefault(pkg, set()).add(self)
        self.state = state

class InstalledPackages:
    """Collection of packages and theit interpretation as comps groups."""
    def __init__(self, yumobj=None, input=None, pkgs=None, ignore_missing=False):
        """
        @param yumobj(optional): use this instance of YumBase
        @param input(optional): read package names from this file
        @param pkgs(optional): use this iterable of package names
        @param ignore_missing: exlcude packages not found in the repos
        """

        if yumobj is None:
            yumobj = yum.YumBase()
            yumobj.preconf.debuglevel = 0
            yumobj.setCacheDir()
        self.yum = yumobj
        self.groups = []
        self.pkg2group = {}
        self.input = input
        self.__buildList(pkgs, ignore_missing)

    def __addGroup(self, group):
        g = Group(group, self.yum)
        g._buildSets(self.leaves.copy(), self.allpkgs.copy())
        self.groups.append(g)

    def __evrTupletoVer(self,tup):
        """convert an evr tuple to a version string, return None if nothing
        to convert"""
        e, v, r = tup
        if v is None:
            return None
        val = v
        if e is not None:
            val = '%s:%s' % (e, v)
        if r is not None:
            val = '%s-%s' % (val, r)
        return val

    def __getLeaves(self, pkgnames):
        pkgs = set()
        missing = set()
        for name in pkgnames:
            try:
                found =  self.yum.pkgSack.returnNewestByName(name)
                pkgs.update(found) # XXX select proper arch!
            except yum.Errors.PackageSackError, e:
                missing.add(name)
        nonleaves = set()
        for pkg in pkgs:
            for (req, flags, (reqe, reqv, reqr)) in pkg.returnPrco('requires'):
                if req.startswith('rpmlib('): continue # ignore rpmlib deps

                ver = self.__evrTupletoVer((reqe, reqv, reqr))
                try:
                    resolve_sack = self.yum.whatProvides(req, flags, ver)
                except yum.Errors.RepoError, e:
                    continue
                for p in resolve_sack:
                    if p is pkg or p.name == pkg.name:
                        continue
                    nonleaves.add(p.name)
        return pkgnames - nonleaves, missing

    def __buildList(self, pkgs=None, ignore_missing=False):
        if pkgs:
            self.allpkgs = frozenset(pkgs)
        elif self.input is None:
            self.allpkgs = frozenset(pkg.name for pkg in self.yum.rpmdb.returnPackages())
        else:
            pkgs = []
            for line in self.input:
                pkgs.extend(line.split())
            pkgs = map(str.strip, pkgs)
            pkgs = filter(None, pkgs)
            self.allpkgs = frozenset(pkgs)

        if self.input is None and not ignore_missing and not pkgs:
            self.leaves = frozenset((pkg.name for pkg in self.yum.rpmdb.returnLeafNodes()))
        else:
            leaves, missing = self.__getLeaves(self.allpkgs)
            if ignore_missing:
                self.leaves = leaves - missing
                self.allpkgs = self.allpkgs - missing
            else:
                self.leaves = leaves

        self.leafcount = len(self.leaves)

        # check if package exist in repository
        self.missingpkgs = set()
        for pkg in self.allpkgs:
            if self.yum.pkgSack.searchNames([pkg]):
                continue
            self.missingpkgs.add(pkg)

        for group in self.yum.comps.get_groups():
            self.__addGroup(group)

    def autodetectStates(self, allowexcludes=False, allowed=("default",)):
        """Check with states (None, "mandatory", "default", "all") is the best
        for each of the groups.
        @param allowexcludes: use excludes for groups not installable as
                              a whole
        @param allowed: list of states that are considered
        """
        pkg2group = {}
        for g in self.groups:
            g._autodetectState(allowexcludes, allowed)
            # find out which pkgs are in more than one group
            for pkg in g.add:
                pkg2group.setdefault(pkg, set()).add(g)
        for g in self.groups:
            # filter out groups which are not worth it because some of
            # their packages belong to other groups
            # This is likely a NP complete problem, but this is a very
            # simple algorithm. Results may be below the optimum.
            g._autodetectState(allowexcludes, allowed, self.pkg2group)

    def globalExcludes(self):
        """return a list of all excludes"""
        excludes = set()
        for g in self.groups:
            excludes.update(g.exclude)
        return excludes

    def remainingPkgs(self, all=False):
        """Return a list of all packages not parts of groups
        or required by others
        @param all: return the addons of the groups, too
        """
        remaining = set(self.leaves)
        for g in self.groups:
            remaining.difference_update(g.add)
            if not all:
                remaining.difference_update(g.addons)
        return remaining

class ListPrinter:
    """Writes things out. Closely coupled to the optparse object
    created in the main function.
    """
    def __init__(self, pkgs, options, output=None):
        self.pkgs = pkgs
        if output is None:
            output = sys.stdout
        self.output = output
        self.options = options
        self.__seen = set()

    def __printPkgs(self, pkgs, prefix='', separator='\n'):
        pkgs = pkgs - self.__seen
        self.__seen.update(pkgs)
        pkgs = list(pkgs)
        pkgs.sort()
        for name in pkgs:
            self.output.write("%s%s%s" % (prefix, name, separator))
        return len(pkgs)

    def writeWarnings(self):
        e = sys.stderr
        if self.pkgs.missingpkgs:
            e.write("WARNING: The following packages are installed but not in the repository:\n")
            for pkg in self.pkgs.missingpkgs:
                e.write("\t%s\n" % pkg)
            e.write("\n")

        if True:
            first = True
            for g in self.pkgs.groups:
                if not g.excludeMissing:
                    continue
                if first:
                    e.write("WARNING: The following groups contain packages not found in the repositories:\n")
                    first = False
                e.write("%s%s\n" % ("XXX ", g.id))
                for pkg in g.excludeMissing:
                    e.write("\t%s\n" % pkg)
            if not first:
                e.write("\n")

    def writeList(self):
        self.__seen.clear()
        if self.options.format == "human":
            indent = '\t'
            separator = '\n'
        elif self.options.format == "kickstart":
            indent = ''
            separator = '\n'
        elif self.options.format == "yum":
            indent = ''
            separator = ' '
        else:
            raise ValueError("Unknown format")

        remaining = self.pkgs.remainingPkgs(True)

        lines = 0
        groups = 0
        for group in self.pkgs.groups:
            addons = group.addons & remaining
            if not group.state and not(
                addons and self.options.addons_by_group and
                not self.options.global_addons):
                continue
            lines += 1
            if group.state:
                groups += 1

            self.output.write("%s%s%s" % (state2str(group), group.id, separator))
            # exclude lines after the group
            if not self.options.global_excludes:
                pkgs = group.exclude
                if self.options.ignore_missing_excludes:
                    pkgs = pkgs - group.excludeMissing
                lines += self.__printPkgs(pkgs, indent+'-', separator)
            # packages after the group
            if not self.options.global_addons:
                lines += self.__printPkgs(addons, indent, separator)

        if self.options.format == "human":
            lines += 1
            self.output.write("# Others\n")

        # leave filtering out pkgs bmeantioned above to __printPkgs
        lines += self.__printPkgs(remaining, '', separator)

        # exclude lines at the end
        excludes = self.pkgs.globalExcludes()
        if self.options.global_excludes:
            lines += self.__printPkgs(excludes, '-', separator)
        # Stats
        if self.options.format == "human":
            lines += 3
            self.output.write("# %i package names, %i leaves\n# %i groups, %i leftovers, %i excludes\n# %i lines\n" % (len(self.pkgs.allpkgs), len(self.pkgs.leaves), groups, len(remaining), len(excludes), lines))

# ****************************************************************************

def __main__():
    parser = OptionParser(description="Gives a compact description of the packages installed (or given) making use of the comps groups found in the repositories.")
    parser.add_option("-f", "--format", dest="format",
                     choices=('kickstart','human','yum'), default="human",
                     help='yum, kickstart or human; yum gives the result as a yum command line; kickstart the content of a %packages section; "human" readable is default.')
    parser.add_option("-i", "--input", dest="input", action="store", default=None, help="File to read the package list from instead of using the rpmdb. - for stdin. The file must contain package names only separated by white space (including newlines). rpm -qa --qf='%{name}\\n' produces proper output.")
    parser.add_option("-o", "--output", dest="output", action="store", default=None, help="File to write the result to. Stdout is used if option is omitted.")
    parser.add_option("-q", "--quiet", dest="quiet", action="store_true", help="Do not show warnings.")
    parser.add_option("-e", "--no-excludes", dest="excludes",
                      action="store_false", default=True,
                      help="Only show groups that are installed completely. Do not use exclude lines.")

    parser.add_option("--global-excludes", dest="global_excludes", action="store_true", help="Print exclude lines at the end and not after the groups requiring them.")
    parser.add_option("--global-addons", dest="global_addons", action="store_true", help="Print package names at the end and not after the groups offering them as addon.")
    parser.add_option('--addons-by-group', dest="addons_by_group", action="store_true", help='Also show groups not selected to sort packages contained by them. Those groups are commented out with a "# " at the begin of the line.')

    parser.add_option("-m", "--allow-mandatories", dest="allowed", action="append_const", const='mandatory', default=['default'], help='Check if just installing the mandatory packages gives better results. Uses "." to mark those groups.')
    parser.add_option("-a", "--allow-all", dest="allowed", action='append_const', const='all', help='Check if installing all packages in the groups gives better results. Uses "*" to mark those groups.')
    parser.add_option("--ignore-missing", dest="ignore_missing", action="store_true", help="Ignore packages missing in the repos.")
    parser.add_option("--ignore-missing-excludes", dest="ignore_missing_excludes", action="store_true", help="Do not produce exclude lines for packages not in the repository.")

    (options, args) = parser.parse_args()

    if options.format != "human" and len(options.allowed)>1:
        print '-m, --allow-mandatories, -a, --allow-all are only allowed in "human" (readable) format as yum and anaconda do not support installing all or only mandatory packages per group. Sorry.'
        sys.exit(-1)

    input_ = None
    if options.input and options.input=="-":
        input_ = sys.stdin
    elif options.input:
        try:
            input_ = open(options.input)
        except IOError, e:
            print e
            exit -1
    else:
        input_ = None
    if options.output and options.output!='-':
        output = open(options.output, "w")
    else:
        output = sys.stdout

    i = InstalledPackages(input=input_, ignore_missing=options.ignore_missing)
    i.autodetectStates(options.excludes, options.allowed)

    p = ListPrinter(i, options, output=output)
    if not options.quiet:
        p.writeWarnings()
    p.writeList()

if __name__ == "__main__":
    __main__()

#!/usr/bin/python
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
# (c) 2005 Panu Matilainen <pmatilai@laiskiainen.org>

# generates graphviz .dot's from repomd data
# usage something like
# $ ./repo-graph.py --repoid=base > foo.dot
# $ neato -v -Gmaxiter=2000 -x -Gcenter=false -Goverlap=scale -Tps2 -o foo.ps foo.dot

import yum
import sys
from yum.misc import getCacheDir
from optparse import OptionParser

default_header = """
size="20.69,25.52";
ratio="fill";
rankdir="TB";
orientation=port;
node[style="filled"];
"""

class yumQuiet(yum.YumBase):

    def doDot(self, header):
        maxdeps = 0
        deps = self.getDeps()

        print 'digraph packages {',
        print '%s' % header

        for pkg in deps.keys():
            if len(deps[pkg]) > maxdeps:
                maxdeps=len(deps[pkg])

            # color calculations lifted from rpmgraph 
            h=0.5+(0.6/23*len(deps[pkg]))
            s=h+0.1
            b=1.0
            
            print '"%s" [color="%s %s %s"];' % (pkg, h, s, b)
            print '"%s" -> {' % pkg
            for req in deps[pkg]:
                print '"%s"' % req
            print '} [color="%s %s %s"];\n' % (h, s, b)
        print "}"
            
    def getDeps(self):
        requires = {}
        prov = {}
        cached = 0
        looked_up = 0
        skip = []

        for pkg in my.pkgSack.returnPackages():
            xx = {}
            for r in pkg.returnPrco('requires'):
                reqname = r[0]
                if reqname.startswith('rpmlib'): continue
                if reqname in prov:
                    provider = prov[reqname]
                    cached += 1
                else:
                    provider = my.pkgSack.searchProvides(reqname)
                    looked_up += 1
                    if not provider:
                        #print "XXXX nothing provides", reqname
                        continue
                    else:
                        provider = provider[0].name
                    prov[reqname] = provider
                if provider == pkg.name:
                    xx[provider] = None
                if provider in xx or provider in skip:
                    continue
                else:
                    xx[provider] = None
                requires[pkg.name] = xx.keys()

        #print >> sys.stderr, "looked up %d providers: " % looked_up
        #print >> sys.stderr, "%d providers from cache: " % cached
        return requires

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("--repoid", default=[], action="append",
                      help="specify repositories to use")
    parser.add_option("-c", dest="conffile", action="store",
                      default="/etc/yum.conf", help="config file location")
    #parser.add_option("--header", dest="header", action="store",
    #                  help="specify alternative .dot header")
    (opts, args) = parser.parse_args()

    my = yumQuiet()
    my.doConfigSetup(opts.conffile, init_plugins=False)
    cachedir = getCacheDir()
    my.repos.setCacheDir(cachedir)

    if len(opts.repoid) > 0:
        for repo in my.repos.findRepos('*'):
            if repo.id not in opts.repoid:
                repo.disable()
            else:
                repo.enable()
    try:
        my.doRepoSetup()
        my.doTsSetup()
        my.doSackSetup()

        my.doDot(default_header)
    except yum.Errors.YumBaseError, e:
        print "Encountered an error creating graph: %s" % e
        sys.exit(1)
        

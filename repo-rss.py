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
# seth vidal 2005 (c) etc etc

import yum
import yum.Errors
from yum.misc import getCacheDir, to_unicode
from yum.comps import Comps, CompsException
from yum.Errors import RepoMDError
import sys
import os
import libxml2
import time
from optparse import OptionParser

class YumQuiet(yum.YumBase):
    def __init__(self):
        yum.YumBase.__init__(self)
    
    def getRecent(self, days=1):
        """return most recent packages from sack"""

        recent = []
        now = time.time()
        recentlimit = now-(days*86400)
        ftimehash = {}
        if self.conf.showdupesfromrepos:
            avail = self.pkgSack.returnPackages()
        else:
            avail = self.pkgSack.returnNewestByNameArch()
        
        for po in avail:
            ftime = int(po.returnSimple('filetime'))
            if ftime > recentlimit:
                if ftime not in ftimehash:
                    ftimehash[ftime] = [po]
                else:
                    ftimehash[ftime].append(po)

        for sometime in ftimehash.keys():
            for po in ftimehash[sometime]:
                recent.append(po)
        
        return recent

class RepoRSS:
    def __init__(self, fn='repo-rss.xml'):
        self.description = 'Repository RSS'
        self.link = 'http://yum.baseurl.org'
        self.title = 'Recent Packages'
        self.doFile(fn)
        self.doDoc()
        
    def doFile(self, fn):
        if fn[0] != '/':
            cwd = os.getcwd()
            self.fn = os.path.join(cwd, fn)
        else:
            self.fn = fn
        try:
            self.fo = open(self.fn, 'w')
        except IOError, e:
            print >> sys.stderr, "Error opening file %s: %s" % (self.fn, e)
            sys.exit(1)

    def doDoc(self):
        """sets up our doc and rssnode attribute initially, rssnode will be
           redfined as we move along"""
        self.doc = libxml2.newDoc('1.0')
        self.xmlescape = self.doc.encodeEntitiesReentrant
        rss = self.doc.newChild(None, 'rss', None)
        rss.setProp('version', '2.0')
        self.rssnode = rss.newChild(None, 'channel', None)

    def startRSS(self):
        """return string representation of rss preamble"""
    
        rfc822_format = "%a, %d %b %Y %X GMT"
        now = time.strftime(rfc822_format, time.gmtime())
        rssheader = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <title>%s</title>
        <link>%s</link>
        <description>%s</description>
        <pubDate>%s</pubDate>
        <generator>Yum</generator>
        """ % (self.title, self.link, self.description, now)
        
        self.fo.write(rssheader)
    
    
    def doPkg(self, pkg, url):
        item = self.rsspkg(pkg, url)
        self.fo.write(item.serialize("utf-8", 1))
        item.unlinkNode()
        item.freeNode()
        del item
    
        
    def rsspkg(self, pkg, url):
        """takes a pkg object and repourl for the pkg object"""
        
        rfc822_format = "%a, %d %b %Y %X GMT"
        clog_format = "%a, %d %b %Y GMT"
        escape = self.xmlescape
        
        item = self.rssnode.newChild(None, 'item', None)
        title = escape(str(pkg))
        item.newChild(None, 'title', title)
        date = time.gmtime(float(pkg.returnSimple('buildtime')))
        item.newChild(None, 'pubDate', time.strftime(rfc822_format, date))
        item.newChild(None, 'guid', pkg.returnSimple('id')).setProp("isPermaLink", "false")        
        link = url + '/' + pkg.returnSimple('relativepath')
        item.newChild(None, 'link', escape(link))
    
        # build up changelog
        changelog = ''
        cnt = 0
        if (pkg.changelog != None):
            where = pkg.changelog
        else:
            where = pkg.returnChangelog()
        for e in where:
            cnt += 1
            if cnt > 3: 
                changelog += '...'
                break
            (date, author, desc) = e
            date = time.strftime(clog_format, time.gmtime(float(date)))
            changelog += '%s - %s\n%s\n\n' % (date, author, desc)
        description = '<p><strong>%s</strong> - %s</p>\n\n' % (escape(pkg.name), 
                                            escape(pkg.returnSimple('summary')))
        description += '<p>%s</p>\n\n<p><strong>Change Log:</strong></p>\n\n' % escape(to_unicode(pkg.returnSimple('description')).encode('utf-8').replace("\n", "<br />\n"))
        description += escape('<pre>%s</pre>' % escape(to_unicode(changelog).encode('utf-8')))
        item.newChild(None, 'description', description)
        
        return item
        

    def closeRSS(self):
        """end the rss output"""
        
        end="\n  </channel>\n</rss>\n"
        self.fo.write(end)
        self.fo.close()
        del self.fo
        self.doc.freeDoc()
        del self.doc
    
    
def makeFeed(filename, title, link, description, recent, my):
    rssobj = RepoRSS(fn=filename)
    rssobj.title = title
    rssobj.link = link
    rssobj.description = description
    rssobj.startRSS()
    # take recent updates only and dump to an rss compat output
    if len(recent) > 0:
        for pkg in recent:
            repo = my.repos.getRepo(pkg.repoid)
            url = repo.urls[0]
            rssobj.doPkg(pkg, url)
    rssobj.closeRSS()


def main(options, args):
    days = options.days
    repoids = args
    my = YumQuiet()
    if options.config:
        my.doConfigSetup(init_plugins=False, fn=options.config)
    else:
        my.doConfigSetup(init_plugins=False)

    if os.geteuid() != 0 or options.tempcache:
        cachedir = getCacheDir()
        if cachedir is None:
            print "Error: Could not make cachedir, exiting"
            sys.exit(50)
        my.repos.setCacheDir(cachedir)

    if len(repoids) > 0:
        for repo in my.repos.repos.values():
            if repo.id not in repoids:
                repo.disable()
            else:
                repo.enable()

    try:
        my._getRepos()
    except yum.Errors.RepoError, e:
        print >> sys.stderr, '%s' % e
        print 'Cannot continue'
        sys.exit(1)
    print 'Reading in repository metadata - please wait....'
    if len(options.arches):
        my._getSacks(archlist=options.arches)
    else:
        my._getSacks()

    for repo in my.repos.listEnabled():
            
        try:
            my.repos.populateSack(which=[repo.id], mdtype='otherdata')
        except yum.Errors.RepoError, e:
            print >> sys.stderr, 'otherdata not available for repo: %s' % repo
            print >> sys.stderr, 'run as root to get changelog data'
            sys.exit(1)
    
    recent = my.getRecent(days=days)
    recent.sort(key=lambda pkg: pkg.returnSimple('filetime'))
    recent.reverse()
    if options.groups:
        comps = Comps()
        for repo in my.repos.listEnabled():
            try: 
                groupsfn = repo.getGroups()
            except RepoMDError: # no comps.xml file
                groupsfn = None
            if not groupsfn:
                continue
            try:
                comps.add(groupsfn)
            except (AttributeError, CompsException):
                print 'Error parsing comps file %s !' % groupsfn
                print 'Multiple feed generation impossible.'
                sys.exit(1)
        for group in comps.groups:
            grouppkgs = group.optional_packages.keys() + group.default_packages.keys() + group.conditional_packages.keys()
            title = "%s - %s" % (options.title, group.name)
            description = "%s. %s" % (options.description, group.name)
            filename = "%s.xml" % group.groupid
            packages = [ pkg for pkg in recent if pkg.name in grouppkgs ]
            makeFeed(filename, title, options.link, description, packages, my)
    # Always make a full feed
    makeFeed(options.filename, options.title, options.link, options.description, recent, my)
    


if __name__ == "__main__":
    usage = "repo-rss.py [options] repoid1 repoid2"
    
    parser = OptionParser(usage=usage)
    parser.add_option("-f", action="store", type="string", dest="filename",
                      default='repo-rss.xml', help="filename to write rss to: %default")
    parser.add_option("-l", action="store", type='string', dest='link',
                      default='http://yum.baseurl.org',
                      help="url for rss feed link: %default")
    parser.add_option("-t", action='store', type='string', dest='title',
                      default="RSS Repository - Recent Packages",
                      help='Title for Rss feed: %default')
    parser.add_option("-d", action='store', type='string', dest='description',
                      default="Most recent packages in Repositories",
                      help='description of feed: %default')
    parser.add_option('-r', action='store', type='int', dest='days', default=3,
                      help='most recent (in days): %default')
    parser.add_option("--tempcache", default=False, action="store_true",
                      help="Use a temp dir for storing/accessing yum-cache")
    parser.add_option("-g", action='store_true', dest='groups', default=False,
                      help="Generate one feed per package group")
    parser.add_option("-a", action='append', dest='arches', default=[],
                      help="arches to use - can be listed more than once")
    parser.add_option("-c", action='store', dest='config', default=None,
                      help="config file")
    (options, args) = parser.parse_args()

    main(options, args)


#!/usr/bin/python

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
# seth vidal 2005 (c) etc etc

import yum
import yum.Errors
import sys
import os
import libxml2
import time
from optparse import OptionParser


class YumQuiet(yum.YumBase):
    def __init__(self):
        yum.YumBase.__init__(self)
    
    def log(self, value, msg):
        pass

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
                if not ftimehash.has_key(ftime):
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
        self.link = 'http://linux.duke.edu/projects/yum'
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
        xhtml_ns = "http://www.w3.org/1999/xhtml"
        escape = self.xmlescape
        
        item = self.rssnode.newChild(None, 'item', None)
        title = escape(str(pkg))
        item.newChild(None, 'title', title)
        date = time.gmtime(float(pkg.returnSimple('buildtime')))
        item.newChild(None, 'pubDate', time.strftime(rfc822_format, date))
        item.newChild(None, 'guid', pkg.returnSimple('id'))
        link = url + '/' + pkg.returnSimple('relativepath')
        item.newChild(None, 'link', escape(link))
    
        # build up changelog
        changelog = ''
        cnt = 0
        for e in pkg.changelog:
            cnt += 1
            if cnt > 3: 
                changelog += '...'
                break
            (date, author, desc) = e
            date = time.strftime(clog_format, time.gmtime(float(date)))
            changelog += '%s - %s\n%s\n\n' % (date, author, desc)
        body = item.newChild(None, "body", None)
        body.newNs(xhtml_ns, None)
        body.newChild(None, "p", escape(pkg.returnSimple('summary')))
        body.newChild(None, "pre", escape(pkg.returnSimple('description')))
        body.newChild(None, "p", 'Change Log:')
        body.newChild(None, "pre", escape(changelog))
        description = '<pre>%s - %s\n\n' % (escape(pkg.name), 
                                            escape(pkg.returnSimple('summary')))
        description += '%s\n\nChange Log:\n\n</pre>' % escape(pkg.returnSimple('description'))
        description += escape('<pre>%s</pre>' % escape(changelog))
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

def main(options, args):
    days = options.days
    repoids = args
    my = YumQuiet()
    my.doConfigSetup()
    if os.geteuid() != 0:
        my.conf.setConfigOption('cache', 1)
        print 'Not running as root, might not be able to import all of cache'

    if len(repoids) > 0:
        for repo in my.repos.repos.values():
            if repo.id not in repoids:
                repo.disable()
            else:
                repo.enable()

    try:
        my.doRepoSetup()
    except yum.Errors.RepoError, e:
        print >> sys.stderr, '%s' % e
        print 'Cannot continue'
        sys.exit(1)
    print 'Reading in repository metadata - please wait....'
    my.doSackSetup()
    for repo in my.repos.listEnabled():
            
        try:
            my.repos.populateSack(which=[repo.id], with='otherdata')
        except yum.Errors.RepoError, e:
            print >> sys.stderr, 'otherdata not available for repo: %s' % repo
            print >> sys.stderr, 'run as root to get changelog data'
            sys.exit(1)
    
    recent = my.getRecent(days=days)
    rssobj = RepoRSS(fn=options.filename)
    rssobj.title = options.title
    rssobj.link = options.link
    rssobj.description = options.description
    rssobj.startRSS()
    
    # take recent updates only and dump to an rss compat output
    if len(recent) > 0:
        for pkg in recent:
            repo = my.repos.getRepo(pkg.repoid)
            url = repo.urls[0]
            rssobj.doPkg(pkg, url)
        
    rssobj.closeRSS()


if __name__ == "__main__":
    usage = "usage: repo-rss.py [options] repoid1 repoid2"
    
    parser = OptionParser(usage=usage)
    parser.add_option("-f", action="store", type="string", dest="filename",
                      default='repo-rss.xml', help="filename to write rss to: %default")
    parser.add_option("-l", action="store", type='string', dest='link',
                      default='http://linux.duke.edu/projects/yum/',
                      help="url for rss feed link: %default")
    parser.add_option("-t", action='store', type='string', dest='title',
                      default="RSS Repository - Recent Packages",
                      help='Title for Rss feed: %default')
    parser.add_option("-d", action='store', type='string', dest='description',
                      default="Most recent packages in Repositories",
                      help='description of feed: %default')
    parser.add_option('-r', action='store', type='int', dest='days', default=3,
                      help='most recent (in days): %default')
    (options, args) = parser.parse_args()

    main(options, args)


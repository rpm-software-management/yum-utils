#!/usr/bin/python -tt

import os, os.path
import sys
import re
import yum
sys.path.insert(0,'/usr/share/yum-cli')
from utils import YumUtilBase
import logging
import fnmatch

from iniparse import INIConfig
import yum.config
import yum.yumRepo

from yum.parser import varReplace

# Regular expressions to sanitise cache filenames
re_url_scheme    = re.compile(r'^\w+:/*(\w+:|www\.)?')
re_slash         = re.compile(r'[?/:&#|]+')
re_initial_cruft = re.compile(r'^[,.]*')
re_final_cruft   = re.compile(r'[,.]*$')

def sanitize_url_to_fs(url):
    """Return a filename suitable for the filesystem

    Strips dangerous and common characters to create a filename we
    can use to store the cache in.
    """
    
    # code taken and modified from planet venus code base:
    # http://intertwingly.net/code/venus/LICENCE

    try:
        if re_url_scheme.match(url):
            if isinstance(url,str):
                url=url.decode('utf-8').encode('idna')
            else:
                url=url.encode('idna')
    except:
        pass
    if isinstance(url,unicode):
        url=url.encode('utf-8')
    url = re_url_scheme.sub("", url)
    url = re_slash.sub("_", url)
    url = re_initial_cruft.sub("", url)
    url = re_final_cruft.sub("", url)

    # limit length of url
    if len(url)>250:
        parts=url.split(',')
        for i in range(len(parts),0,-1):
            if len(','.join(parts[:i])) < 220:
                url = ','.join(parts[:i]) + ',' + \
                    yum.misc.checksum('md5', (','.join(parts[i:])))
                break

    return url



def writeRawConfigFile(filename, section_id, yumvar,
                       cfgoptions, items, optionobj,
                       only=None):
    """
    From writeRawRepoFile, but so we can alter [main] too.
    """
    ini = INIConfig(open(filename))

    osection_id = section_id
    # b/c repoids can have $values in them we need to map both ways to figure
    # out which one is which
    if section_id not in ini._sections:
        for sect in ini._sections.keys():
            if varReplace(sect, yumvar) == section_id:
                section_id = sect

    # Updated the ConfigParser with the changed values
    cfgOptions = cfgoptions(osection_id)
    for name,value in items():
        if value is None: # Proxy
            continue

        if only is not None and name not in only:
            continue

        option = optionobj(name)
        ovalue = option.tostring(value)
        #  If the value is the same, but just interpreted ... when we don't want
        # to keep the interpreted values.
        if (name in ini[section_id] and
            ovalue == varReplace(ini[section_id][name], yumvar)):
            ovalue = ini[section_id][name]

        if name not in cfgOptions and option.default == value:
            continue

        ini[section_id][name] = ovalue
    fp =file(filename, "w")
    fp.write(str(ini))
    fp.close()

def match_repoid(repoid, repo_setopts):
    for i in repo_setopts:
        if fnmatch.fnmatch(repoid, i):
            return True

NAME = 'yum-config-manager'
VERSION = '1.0'
USAGE = '"yum-config-manager [options] [section]'

yum.misc.setup_locale()

yb = YumUtilBase(NAME, VERSION, USAGE)
logger = logging.getLogger("yum.verbose.cli.yum-config-manager")
yb.preconf.debuglevel = 0
yb.preconf.errorlevel = 0
yb.optparser = yb.getOptionParser()
if hasattr(yb, 'getOptionGroup'): # check if the group option API is available
    group = yb.getOptionGroup()
else:
    group = yb.optparser
group.add_option("--save", default=False, action="store_true",
          help='save the current options (useful with --setopt)')
group.add_option("--enable", default=False, action="store_true",
          help='enable the specified repos (automatically saves)')
group.add_option("--disable", default=False, action="store_true",
          help='disable the specified repos (automatically saves)')
group.add_option("--add-repo", default=[], dest='addrepo', action='append',
          help='add (and enable) the repo from the specified file or url')
try:
    opts = yb.doUtilConfigSetup()
    yb.repos
except yum.Errors.YumBaseError, e:
    logger.error(str(e))
    sys.exit(50)

if opts.save or opts.enable or opts.disable or opts.addrepo:
    if yb.conf.uid != 0:
        logger.error("You must be root to change the yum configuration.")
        sys.exit(50)
        
args = set(yb.cmds)

if opts.enable and opts.disable:
    logger.error("Error: Trying to enable and disable repos.")
    opts.enable = opts.disable = False
if opts.enable and not args:
    logger.error("Error: Trying to enable already enabled repos.")
    opts.enable = False

only = None

if (not args and not opts.addrepo) or 'main' in args:
    print yb.fmtSection('main')
    print yb.conf.dump()
    if opts.save and hasattr(yb, 'main_setopts') and yb.main_setopts:
        fn = '/etc/yum/yum.conf'
        if not os.path.exists(fn):
            # Try the old default
            fn = '/etc/yum.conf'
        ybc = yb.conf
        writeRawConfigFile(fn, 'main', ybc.yumvar,
                           ybc.cfg.options, ybc.iteritems, ybc.optionobj,
                           only=yb.main_setopts.items)

if opts.enable or opts.disable:
    opts.save = True
    if not hasattr(yb, 'repo_setopts') or not yb.repo_setopts:
        only = ['enabled']

if args:
    repos = yb.repos.findRepos(','.join(args),
                               name_match=True, ignore_case=True)
else:
    repos = yb.repos.listEnabled()

if not opts.addrepo:
    for repo in sorted(repos):
        print yb.fmtSection('repo: ' + repo.id)
        if opts.enable and not repo.enabled:
            repo.enable()
        elif opts.disable and repo.enabled:
            repo.disable()
        print repo.dump()
        if (opts.save and
            (only or (hasattr(yb, 'repo_setopts') and match_repoid(repo.id, yb.repo_setopts)))):
            writeRawConfigFile(repo.repofile, repo.id, repo.yumvar,
                               repo.cfg.options, repo.iteritems, repo.optionobj,
                               only)

if opts.addrepo:
    # figure out the best reposdir by seeing which dirs exist
    myrepodir = None
    for rdir in yb.conf.reposdir:
        if os.path.exists(rdir): # take the first one that exists
            myrepodir = rdir
            break
    
    if not myrepodir:
        myrepodir = yb.conf.reposdir[0]
        os.makedirs(myrepodir)
        
    for url in opts.addrepo:
        print 'adding repo from: %s' % url
        if url.endswith('.repo'): # this is a .repo file - fetch it, put it in our reposdir and enable it
            destname = os.path.basename(url)
            destname = myrepodir + '/' + destname

            # dummy grabfunc, using [main] options
            repo = yum.yumRepo.YumRepository('dummy')
            repo.baseurl = ['http://dummy']
            repo.populate(yum.config.ConfigParser(), None, yb.conf)
            grabber = repo.grabfunc; del repo

            print 'grabbing file %s to %s' % (url, destname)
            try:
                result  = grabber.urlgrab(url, filename=destname, copy_local=True, reget=None)
            except (IOError, OSError, yum.Errors.YumBaseError), e:
                logger.error('Could not fetch/save url %s to file %s: %s'  % (url, destname, e))
                continue
            else:
                print 'repo saved to %s' % result
            
        else:
            repoid = sanitize_url_to_fs(url)
            reponame = 'added from: %s' % url
            repofile = myrepodir + '/' + repoid + '.repo'
            try:
                thisrepo = yb.add_enable_repo(repoid, baseurl=[url], name=reponame)
            except yum.Errors.DuplicateRepoError, e:
                logger.error('Cannot add repo from %s as is a duplicate of an existing repo' % url)
                continue
            repoout = """\n[%s]\nname=%s\nbaseurl=%s\nenabled=1\n\n""" % (repoid, reponame, url)

            try:
                fo = open(repofile, 'w+')
                fo.write(repoout)
                print repoout
            except (IOError, OSError), e:
                logger.error('Could not save repo to repofile %s: %s' % (repofile, e))
                continue
            else:
                fo.close()
                
            


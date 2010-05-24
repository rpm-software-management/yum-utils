#!/usr/bin/python -tt

import os, os.path
import sys
import yum
sys.path.insert(0,'/usr/share/yum-cli')
from utils import YumUtilBase
import logging

from iniparse import INIConfig

def writeRawConfigFile(filename, sectionname, cfgoptions, items, optionobj,
                       only=None):
    """
    From writeRawRepoFile, but so we can alter [main] too.
    """
    ini = INIConfig(open(filename))
    # Updated the ConfigParser with the changed values
    cfgOptions = cfgoptions(sectionname)
    for name,value in items():
        if value is None: # Proxy
            continue
        option = optionobj(name)
        if option.default != value or name in cfgOptions :
            if only is None or name in only:
                ini[sectionname][name] = option.tostring(value)
    fp =file(filename, "w")
    fp.write(str(ini))
    fp.close()

NAME = 'yum-config-manager'
VERSION = '1.0'
USAGE = '"yum-config-manager [options] [section]'

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

try:
    opts = yb.doUtilConfigSetup()
except yum.Errors.RepoError, e:
    logger.error(str(e))
    sys.exit(50)

args = set(yb.cmds)

if opts.enable and opts.disable:
    logger.error("Error: Trying to enable and disable repos.")
    opts.enable = opts.disable = False
if opts.enable and not args:
    logger.error("Error: Trying to enable already enabled repos.")
    opts.enable = False

only = None

if not args or 'main' in args:
    print yb.fmtSection('main')
    print yb.conf.dump()
    if opts.save and hasattr(yb, 'main_setopts') and yb.main_setopts:
        fn = '/etc/yum/yum.conf'
        if not os.path.exists(fn):
            # Try the old default
            fn = '/etc/yum.conf'
        ybc = yb.conf
        writeRawConfigFile(fn, 'main',
                           ybc.cfg.options, ybc.iteritems, ybc.optionobj,
                           only)

if opts.enable or opts.disable:
    opts.save = True
    if not hasattr(yb, 'repo_setopts') or not yb.repo_setopts:
        only = ['enabled']

if args:
    repos = yb.repos.findRepos(','.join(args))
else:
    repos = yb.repos.listEnabled()

for repo in sorted(repos):
    print yb.fmtSection('repo: ' + repo.id)
    if opts.enable and not repo.enabled:
        repo.enable()
    elif opts.disable and repo.enabled:
        repo.disable()
    print repo.dump()
    if (opts.save and
        (only or (hasattr(yb, 'repo_setopts') and repo.id in yb.repo_setopts))):
        writeRawConfigFile(repo.repofile, repo.id,
                           repo.cfg.options, repo.iteritems, repo.optionobj,
                           only)

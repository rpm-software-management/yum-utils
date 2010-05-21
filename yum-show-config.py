#!/usr/bin/python -tt

import sys
import yum
sys.path.insert(0,'/usr/share/yum-cli')
from utils import YumUtilBase
import logging

NAME = 'yum-show-config'
VERSION = '1.0'
USAGE = '"yum-show-config [options] [section]'

yb = YumUtilBase(NAME, VERSION, USAGE)
logger = logging.getLogger("yum.verbose.cli.yum-show-config")
yb.preconf.debuglevel = 0
yb.preconf.errorlevel = 0
yb.optparser = yb.getOptionParser()
try:
    opts = yb.doUtilConfigSetup()
except yum.Errors.RepoError, e:
    logger.error(str(e))
    sys.exit(50)

args = set(sys.argv[1:])
def _test_arg(x):
    return not args or x in args
        
if _test_arg('main'):
    print yb.fmtSection('main')
    print yb.conf.dump()

for repo in sorted(yb.repos.listEnabled()):
    if not _test_arg(repo.id):
        continue
    print yb.fmtSection('repo: ' + repo.id)
    print repo.dump()

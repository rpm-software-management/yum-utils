from yum.constants import *
from yum.plugins import PluginYumExit
from rpmUtils.miscutils import splitFilename, compareEVR

requires_api_version = '2.1'

def config_hook(conduit):
    conduit.registerOpt('locklist', PLUG_OPT_STRING, PLUG_OPT_WHERE_MAIN, '')

def exclude_hook(conduit):
    conduit.info(2, 'Reading version lock configuration')
    locklist = []
    try:
        llfile = open(conduit.confString('main', 'locklist'))
        for line in llfile.readlines():
            locklist.append(line.rstrip())
        llfile.close()
    except IOError:
        raise PluginYumExit('Unable to read version lock configuration')

    pkgs = conduit.getPackages()
    locked = {}
    for pkg in locklist:
        # Arch doesn't matter but splitFilename wants it so fake it...
        (n, v, r, e, a) = splitFilename("%s.arch" % pkg)
        if e == '': 
            e = '0'
        locked[n] = (e, v, r) 
    for pkg in pkgs:
        if locked.has_key(pkg.name):
            (n, e, v, r, a) = pkg.returnNevraTuple()
            if compareEVR(locked[pkg.name], (e, v, r)) != 0:
                conduit.delPackage(pkg)
                conduit.info(5, 'Excluding package %s due to version lock' % pkg)

requires_api_version = '2.1'

def init_hook(conduit):
    parser = conduit.getOptParser()
    parser.add_option('--tsflags', dest='tsflags')

def postreposetup_hook(conduit):
    opts, args = conduit.getCmdLine()
    conf = conduit.getConf()
    if opts.tsflags:
        flags = opts.tsflags.split(',')
        conf.setConfigOption('tsflags', flags)

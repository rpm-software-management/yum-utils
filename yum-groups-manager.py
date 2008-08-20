#!/usr/bin/python -tt

import os
import sys
import re
import string
import optparse
import gzip

import yum
import yum.comps

sys.path.insert(0, '/usr/share/yum-cli')
import output
from urlgrabber.progress import TextMeter

def setup_opts():
    version = "0.0.1"
    vers_txt = "Create groups data version %s" % version
    usage_txt = "%prog <pkg-wildcard>..."
    parser =  optparse.OptionParser(usage = usage_txt, version = vers_txt)

    parser.add_option("-n", "--name", help="group name")
    parser.add_option("--id", help="group id")

    parser.add_option("--mandatory", action="store_true",
                      help="make the package names be in the mandatory section")
    parser.add_option("--optional", action="store_true",
                      help="make the package names be in the optional section")
    parser.add_option("--dependencies", action="store_true",
                      help="add the dependencies for this package")
    parser.add_option("--not-user-visible", action="store_false", default=True,
                      help="make this a non-user visible group")
    parser.add_option("--description", help="description for the group")
    parser.add_option("--display-order", help="sort order override")

    parser.add_option("--load", action="append", default=[],
                      help="load groups data from file and merge")
    parser.add_option("--save",
                      help="save groups data to file (don't print)")
    parser.add_option("--merge",
                      help="load and save groups data to file (don't print)")
    parser.add_option("--print", dest="print2stdout",
                      action="store_true", default=None,
                      help="print the result to stdout")

    parser.add_option("--translated-name", action="append",
                      dest="i18nname",
                      help="name for the group, translated")
    parser.add_option("--translated-description", action="append",
                      dest="i18ndescription",
                      help="description for the group, translated")

    # Generic options
    parser.add_option("--quiet", action="store_true", 
                      help="quiet (no output to stderr)", default=False)
    parser.add_option("--verbose", action="store_false",
                      help="verbose output", dest="quiet")
    parser.add_option("--enablerepo", action="append", dest="enablerepos",
                      help="specify repoids to query, can be specified multiple times (default is all enabled)")
    parser.add_option("--disablerepo", action="append", dest="disablerepos",
                      help="specify repoids to disable, can be specified multiple times")                      
    # tmprepo etc.
    parser.add_option("--noplugins", action="store_false", default=True,
                      dest="plugins",
                      help="disable yum plugin support")
    parser.add_option("-C", "--cache", action="store_true",
                      help="run from cache only")
    parser.add_option("--tempcache", action="store_true",
                      help="use private cache (default when used as non-root)")
    parser.add_option("-c", dest="conffile", help="config file location")

    return parser

def trans_data(yb, input):
    data = input.split(':', 2)
    if len(data) != 2:
        yb.logger.error("Error: Incorrect translated data, should be: 'lang:text'")
        sys.exit(50)
    lang, text = data
    alnum = string.ascii_letters + string.digits
    lang = re.sub('[^' + alnum + '-_.@]', '', lang)
    if not lang:
        yb.logger.error("Error: Incorrect/empty language for translated data")
        sys.exit(50)
    return lang, text

__req2pkgs = {}
def req2pkgs(yb, req):
    global __req2pkgs

    req = str(req)
    if req in __req2pkgs:
        return __req2pkgs[req]

    providers = []
    try:
        # XXX rhbz#246519, for some reason returnPackagesByDep() fails
        # to find some root level directories while 
        # searchPackageProvides() does... use that for now
        matches = yb.searchPackageProvides([req])
        providers = matches.keys()
        # provider.extend(yum.YumBase.returnPackagesByDep(self, depstring))
    except yum.Errors.YumBaseError, err:
        print >>sys.stderr, "No package provides %s" % req
        return []

    __req2pkgs[req] = providers
    return providers

def main():

    parser = setup_opts()
    (opts, args) = parser.parse_args()
    if len(args) < 1:
        parser.print_help()
        sys.exit(1)

    comps = yum.comps.Comps()

    # Borrowing large sections from repoquery/pkg-tree etc.
    initnoise = (not opts.quiet) * 2
    yb = yum.YumBase()
    yb.doConfigSetup(debuglevel=0, errorlevel=1)
    if opts.conffile:
        yb.doConfigSetup(fn=opts.conffile, debuglevel=initnoise,
                         init_plugins=opts.plugins)
    else:
        yb.doConfigSetup(debuglevel=initnoise, init_plugins=opts.plugins)

    # Show what is going on, if --quiet is not set.
    if not opts.quiet and sys.stdout.isatty():
        yb.repos.setProgressBar(TextMeter(fo=sys.stdout))
        yb.repos.callback = output.CacheProgressCallback()
        yumout = output.YumOutput()
        freport = ( yumout.failureReport, (), {} )
        yb.repos.setFailureCallback( freport )

    if os.geteuid() != 0 or opts.tempcache:
        cachedir = yum.misc.getCacheDir()
        if cachedir is None:
            yb.logger.error("Error: Could not make cachedir, exiting")
            sys.exit(50)
        yb.repos.setCacheDir(cachedir)
        yb.conf.cache = 0 # yum set cache=1, if uid != 0

    if opts.cache:
        yb.conf.cache = True
        if not opts.quiet:
            yb.logger.info('Running from cache, results might be incomplete.')

    if False and opts.show_duplicates:
        yb.conf.showdupesfromrepos = True
        __show_all_versions__ = True
    if opts.disablerepos:
        for repo_match in opts.disablerepos:
            for repo in yb.repos.findRepos(repo_match):
                repo.disable()

    if opts.enablerepos:
        for repo_match in opts.enablerepos:
            for repo in yb.repos.findRepos(repo_match):
                repo.enable()

    try:
        yb.doRepoSetup()
    except yum.Errors.RepoError, e:
        yb.logger.error("Could not setup repo: %s" % (e))
        sys.exit(50)

    archlist = None
    try:
        yb.doSackSetup(archlist=archlist)
    except yum.Errors.RepoError, e:
        yb.logger.error(e)
        sys.exit(1)

    yum.misc.setup_locale()

    if opts.merge:
        opts.load.insert(0, opts.merge)

    for fname in opts.load:
        if not os.path.exists(fname):
            print >>sys.stderr, "File not found:", fname
            continue
        print 'Loading %s' % fname
        if fname.endswith('.gz'):
            fname = gzip.open(cf)
        comps.add(srcfile=fname)

    group = yum.comps.Group()
    if opts.name:
        group.name = opts.name

    if opts.id:
        group.groupid = opts.id
    elif group.name:
        group.groupid = group.name.lower()
        alnum = string.ascii_lowercase + string.digits
        group.groupid = re.sub('[^' + alnum + '-_.:]', '',
                               group.groupid)
    else:
        yb.logger.error("No name or id for group")
        sys.exit(50)

    if opts.description:
        group.description = opts.description
    if opts.display_order:
        group.display_order = int(opts.display_order)
    for tn in opts.i18nname or []:
        lang, text = trans_data(yb, tn)
        group.translated_name[lang] = text
    for td in opts.i18ndescription or []:
        lang, text = trans_data(yb, td)
        group.translated_description[lang] = text

    pkgs     = yb.pkgSack.returnNewestByName(patterns=sys.argv[1:])
    pkgnames = set([pkg.name for pkg in pkgs])

    if opts.dependencies:
        for pkg in pkgs:
            for rptup in pkg.returnPrco('requires'):
                if rptup[0].startswith('rpmlib'):
                    continue
                rname = yum.misc.prco_tuple_to_string(rptup)
                pkgnames.update([pkg.name for pkg in req2pkgs(yb, rname)])

    for pkgname in pkgnames:
        if False: pass
        elif opts.mandatory:
            group.mandatory_packages[pkgname] = 1
        elif opts.optional:
            group.optional_packages[pkgname]  = 1
        else:
            group.default_packages[pkgname]   = 1

    comps.add_group(group)
    if opts.save:
        fo = open(opts.save, "wb")
        fo.write(comps.xml())
        del fo
    if opts.merge:
        fo = open(opts.merge, "wb")
        fo.write(comps.xml())
        del fo

    if (opts.print2stdout or
        (opts.print2stdout is None and not (opts.save or opts.merge))):
        print comps.xml()

if __name__ == "__main__":
    main()

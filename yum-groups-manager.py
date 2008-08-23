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
    vers_txt = "Manage yum groups metadata version %s" % version
    usage_txt = "%prog [pkg-wildcard]..."
    parser =  optparse.OptionParser(usage = usage_txt, version = vers_txt)

    parser.add_option("-n", "--name", help="group name")
    parser.add_option("--id", help="group id")

    parser.add_option("--mandatory", action="store_true",
                      help="make the package names be in the mandatory section")
    parser.add_option("--optional", action="store_true",
                      help="make the package names be in the optional section")
    parser.add_option("--dependencies", action="store_true",
                      help="add the dependencies for this package")
    parser.add_option("--user-visible", dest="user_visible",
                      action="store_true", default=None,
                      help="make this a user visible group (default)")
    parser.add_option("--not-user-visible", dest="user_visible",
                      action="store_false", default=None,
                      help="make this a non-user visible group")
    parser.add_option("--description", help="description for the group")
    parser.add_option("--display-order", help="sort order override")

    parser.add_option("--load", action="append", default=[],
                      help="load groups metadata from file")
    parser.add_option("--save", action="append", default=[],
                      help="save groups metadata to file (don't print)")
    parser.add_option("--merge",
                      help="load and save groups metadata to file (don't print)")
    parser.add_option("--print", dest="print2stdout",
                      action="store_true", default=None,
                      help="print the result to stdout")

    parser.add_option("--remove", action="store_true", default=False,
                      help="remove the listed package instead of adding them")

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
    parser.add_option("-c", "--config",
                      dest="conffile", help="config file location")

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
        yb.logger.error("No package provides %s" % req)
        return []

    __req2pkgs[req] = providers
    return providers

def main():

    parser = setup_opts()
    (opts, args) = parser.parse_args()

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
        opts.save.append(opts.merge)

    loaded_files = False
    for fname in opts.load:
      try:
        if not os.path.exists(fname):
            yb.logger.error("File not found: %s" % fname)
            continue
        if fname.endswith('.gz'):
            fname = gzip.open(cf)
        comps.add(srcfile=fname)
        loaded_files = True
      except IOError, e:
        yb.logger.error(e)
        sys.exit(50)

    if not loaded_files and opts.remove:
        yb.logger.error("Can't remove package(s) when we havn't loaded any")
        sys.exit(50)

    group = None
    if opts.id:
        group = comps.return_group(opts.id)
    if group is None and opts.name:
        group = comps.return_group(opts.name)
    if group is None and opts.remove:
        yb.logger.error("Can't remove package(s) from non-existant group")
        sys.exit(50)

    if group is None:
        group = yum.comps.Group()

        if opts.id:
            group.groupid = opts.id
        elif opts.name:
            group.groupid = opts.name.lower()
            alnum = string.ascii_lowercase + string.digits
            group.groupid = re.sub('[^' + alnum + '-_.:]', '',
                                   group.groupid)
        else:
            yb.logger.error("No name or id for group")
            sys.exit(50)
        comps.add_group(group)

    if opts.name:
        group.name = opts.name
    if opts.description:
        group.description = opts.description
    if opts.display_order:
        group.display_order = int(opts.display_order)
    if opts.user_visible is not None:
        group.user_visible = opts.user_visible
    for tn in opts.i18nname or []:
        lang, text = trans_data(yb, tn)
        group.translated_name[lang] = text
    for td in opts.i18ndescription or []:
        lang, text = trans_data(yb, td)
        group.translated_description[lang] = text

    try:
        if args:
            pkgs = yb.pkgSack.returnNewestByName(patterns=args)
        else:
            pkgs = []
    except yum.packageSack.PackageSackError, e:
        yb.logger.error(e)
        sys.exit(50)

    pkgnames = set([pkg.name for pkg in pkgs])

    if opts.dependencies:
        for pkg in pkgs:
            for rptup in pkg.returnPrco('requires'):
                if rptup[0].startswith('rpmlib'):
                    continue
                rname = yum.misc.prco_tuple_to_string(rptup)
                pkgnames.update([pkg.name for pkg in req2pkgs(yb, rname)])

    for pkgname in pkgnames:
        if opts.remove:
            group.mandatory_packages.pop(pkgname, 0)
            group.optional_packages.pop(pkgname, 0)
            group.default_packages.pop(pkgname, 0)
        elif opts.mandatory:
            group.mandatory_packages[pkgname] = 1
        elif opts.optional:
            group.optional_packages[pkgname]  = 1
        else:
            group.default_packages[pkgname]   = 1

    for fname in opts.save:
      try:
        fo = open(fname, "wb")
        fo.write(comps.xml())
        del fo
      except IOError, e:
        yb.logger.error(e)
        sys.exit(50)

    if (opts.print2stdout or (opts.print2stdout is None and not opts.save)):
        print comps.xml()

if __name__ == "__main__":
    main()

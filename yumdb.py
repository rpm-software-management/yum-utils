#!/usr/bin/python -tt

import sys
import optparse
import fnmatch

import yum
import shlex

import os
import glob

parser = None

# FIXME: Internal knowledge
def _load_all_package_paths(db_path):
    # glob the path and get a dict of pkgs to their subdir
    glb = '%s/*/*/' % db_path
    pkgdirs = glob.glob(glb)
    _packages = {}
    for d in pkgdirs:
        if d[-1] == '/':
            d = d[:-1]
        pkgid = os.path.basename(d).split('-')[0]
        _packages[pkgid] = d
    return _packages

def setup_opts():
    version = "0.0.1"
    vers_txt = "Manage yum groups metadata version %s" % version
    usage_txt = """\
%prog <command> ...
      get           <key> [pkg-wildcard]...
      set           <key> <value> [pkg-wildcard]...
      del           <key> [pkg-wildcard]...
      rename        <key> <key> [pkg-wildcard]...
      rename-force  <key> <key> [pkg-wildcard]...
      copy          <key> <key> [pkg-wildcard]...
      search        <key> <wildcard>...
      exist?        <key> [pkg-wildcard]...
      unset?        <key> [pkg-wildcard]...
      info          [pkg-wildcard]...
      sync          [pkg-wildcard]...
      undeleted
      shell         [filename]...
"""
    parser =  optparse.OptionParser(usage = usage_txt, version = vers_txt)

    parser.add_option("--noplugins", action="store_false", default=True,
                      dest="plugins",
                      help="disable yum plugin support")
    parser.add_option("-c", "--config",
                      dest="conffile", help="config file location")

    return parser

def run_cmd(yb, args, inshell=False):
    if False: pass
    elif args[0] == 'get' and len(args) > 1:
        args.pop(0)
        ykey = args.pop(0)
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            print pkg
            if ykey in pkg.yumdb_info:
                print " " * 4, ykey, '=', getattr(pkg.yumdb_info, ykey)
            else:
                print " " * 4, ykey, '<unset>'
    elif args[0] == 'set' and len(args) > 2:
        args.pop(0)
        ykey = args.pop(0)
        yval = args.pop(0)
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            setattr(pkg.yumdb_info, ykey, yval)
            print pkg
            print " " * 4, ykey, '=', getattr(pkg.yumdb_info, ykey)
    elif args[0] in ('copy', 'copy-f', 'copy-force') and len(args) > 2:
        force = args[0] in ['copy-f', 'copy-force']
        args.pop(0)
        yokey = args.pop(0)
        ynkey = args.pop(0)
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            print pkg
            if yokey in pkg.yumdb_info:
                setattr(pkg.yumdb_info, ynkey, getattr(pkg.yumdb_info, yokey))
                print " " * 4, ynkey, '=', getattr(pkg.yumdb_info, ynkey)
            elif force and ynkey in pkg.yumdb_info:
                delattr(pkg.yumdb_info, ynkey)
                print " " * 4, ynkey, '<unset>'
            elif ynkey in pkg.yumdb_info:
                print " " * 4, ynkey, '=', getattr(pkg.yumdb_info, ynkey)
            else:
                print " " * 4, ynkey, '<unset>'
    elif args[0] in ['rename', 'rename-f', 'rename-force'] and len(args) > 2:
        force = args[0] in ['rename-f', 'rename-force']
        args.pop(0)
        yokey = args.pop(0)
        ynkey = args.pop(0)
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            print pkg
            if yokey in pkg.yumdb_info:
                setattr(pkg.yumdb_info, ynkey, getattr(pkg.yumdb_info, yokey))
                delattr(pkg.yumdb_info, yokey)
                print " " * 4, ynkey, '=', getattr(pkg.yumdb_info, ynkey)
            elif force and ynkey in pkg.yumdb_info:
                delattr(pkg.yumdb_info, ynkey)
                print " " * 4, ynkey, '<unset>'
            elif ynkey in pkg.yumdb_info:
                print " " * 4, ynkey, '=', getattr(pkg.yumdb_info, ynkey)
            else:
                print " " * 4, ynkey, '<unset>'
    elif args[0] in ['del', 'delete', 'rm', 'remove'] and len(args) > 1:
        args.pop(0)
        ykey = args.pop(0)
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            if ykey in pkg.yumdb_info:
                delattr(pkg.yumdb_info, ykey)
            print pkg
            print " " * 4, ykey, '<unset>'
    elif args[0] == 'search' and len(args) > 2:
        args.pop(0)
        ykey = args.pop(0)
        done = False
        # Maybe need some API so we don't have to load everything?
        for pkg in sorted(yb.rpmdb.returnPackages()):
            if ykey not in pkg.yumdb_info:
                continue
            found = False
            yval = getattr(pkg.yumdb_info, ykey)
            for arg in args:
                if fnmatch.fnmatch(yval, arg):
                    found = True
                    break
            if not found:
                continue
            if done: print ''
            done = True
            print pkg
            print " " * 4, ykey, '=', yval
    elif args[0] in ['exist?', 'exist', 'exists'] and len(args) > 1:
        args.pop(0)
        ykey = args.pop(0)
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            if ykey not in pkg.yumdb_info:
                continue
            print pkg
    elif args[0] in ['unset?', 'unset'] and len(args) > 1:
        args.pop(0)
        ykey = args.pop(0)
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            if ykey in pkg.yumdb_info:
                continue
            print pkg
    elif args[0] == 'info':
        args.pop(0)
        done = False
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            if done: print ''
            done = True
            print pkg
            for ykey in sorted(pkg.yumdb_info):
                print " " * 4, ykey, '=', getattr(pkg.yumdb_info, ykey)
    elif args[0] in ('sync', 'synchronize', 'sync-f', 'synchronize-f',
                     'sync-force', 'synchronize-force'):
        force = args[0] in ('sync-f', 'synchronize-f',
                            'sync-force', 'synchronize-force')
        args.pop(0)
        done = False
        for pkg in sorted(yb.rpmdb.returnPackages(patterns=args)):
            apkg = yb.pkgSack.searchPkgTuple(pkg.pkgtup)
            if not apkg:
                continue
            apkg = sorted(apkg)[0]

            if done: print ''
            done = True
            print pkg
            ndata = {}
            ndata['releasever'] = yb.conf.yumvar['releasever']
            ndata['from_repo']  = apkg.repoid
            csum = apkg.returnIdSum()
            if csum is not None:
                ndata['checksum_type'] = str(csum[0])
                ndata['checksum_data'] = str(csum[1])
            if hasattr(apkg.repo, 'repoXML'):
                md = apkg.repo.repoXML
                if md and md.revision is not None:
                    ndata['from_repo_revision']  = str(md.revision)
                if md:
                    ndata['from_repo_timestamp'] = str(md.timestamp)

            loginuid = yum.misc.getloginuid()
            if loginuid is not None:
                ndata['changed_by'] = str(loginuid)

            for ykey in ndata:
                if not force and hasattr(pkg.yumdb_info, ykey):
                    continue
                setattr(pkg.yumdb_info, ykey, ndata[ykey])
            for ykey in sorted(pkg.yumdb_info):
                if ykey not in ndata:
                    continue
                print " " * 4, ykey, '=', getattr(pkg.yumdb_info, ykey)
    elif args[0] == 'undeleted':
        yumdb_packages = _load_all_package_paths(yb.rpmdb.yumdb.conf.db_path)
        for pkg in sorted(yb.rpmdb.returnPackages()):
            if pkg.pkgid in yumdb_packages:
                del yumdb_packages[pkg.pkgid]
        for pkgid in yumdb_packages:
            print "%s: %s" % (pkgid, yumdb_packages[pkgid])

    elif args[0] == 'shell' and not inshell:
        args.pop(0)
        if args:
            fos = []
            for arg in args:
                fos.append(open(arg))
        else:
            fos = [sys.stdin]
        for fo in fos:
            print "=" * 79
            for line in fo:
                run_cmd(yb, shlex.split(line), inshell=True)
                print "-" * 79
    else:
        print >>sys.stderr, parser.format_help()
        sys.exit(1)

def main():
    global parser

    parser = setup_opts()
    (opts, args) = parser.parse_args()

    yb = yum.YumBase()
    if opts.conffile:
        yb.preconf.fn = opts.conffile
    if not opts.plugins:
        yb.preconf.init_plugins = False
    yb.conf

    if len(args) < 1:
        print >>sys.stderr, parser.format_help()
        sys.exit(1)

    run_cmd(yb, args)


if __name__ == '__main__':
    main()

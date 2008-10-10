#!/usr/bin/python -tt

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
## (c) 2008 Red Hat. Written by skvidal@fedoraproject.org

import os
import subprocess
import sys
import yum
from yum import Errors
from rpmUtils import miscutils
import gzip
import rpm
from optparse import OptionParser

# maybe use YumQuiet?

class YumDebugDump(yum.YumBase):

    def __init__(self):
        self.file_version = '1'
        yum.YumBase.__init__(self)
        self.opts = None
        self.args = None
        self.parse_args()

    def parse_args(self):
        parser = OptionParser()
        parser.set_usage("yum-debug-dump [options]")
        parser.add_option("--norepos", action="store_true", default=False,
           help="do not attempt to dump the repository contents")
        self.opts, self.args = parser.parse_args()

    def dump_rpmdb(self):
        msg = "%%%%RPMDB\n"
        for po in self.rpmdb:
            msg += '  %s:%s-%s-%s.%s\n' % (po.epoch, po.name, po.ver,po.rel, po.arch)

        return msg

    def dump_repos(self):
        msg = "%%%%REPOS\n"
        for repo in self.repos.listEnabled():
            try:
                msg += '%%%s - %s\n' % (repo.id, repo.urls[0])
                msg += "  excludes: %s\n" % ",".join(repo.exclude)
                for po in self.pkgSack.returnPackages(repo.id):
                    msg += '  %s:%s-%s-%s.%s\n' % (po.epoch, po.name, po.ver,po.rel, po.arch)
            except Errors.RepoError, e:
                msg += "Error accessing repo %s: %s\n" % (repo, str(e))
                continue
        return msg

    def dump_system_info(self):
        msg = "%%%%SYSTEM INFO\n"
        msg += "  uname: %s, %s\n" % (os.uname()[2], os.uname()[4])
        msg += "  rpm ver: %s\n" % subprocess.Popen(["rpm", "--version"], stdout=subprocess.PIPE).communicate()[0].strip()
        msg += "  python ver: %s\n" % sys.version.replace('\n', '')
        return msg

    def dump_yum_config_info(self):
        msg = "%%%%YUM INFO\n"
        msg += "  arch: %s\n" % self.conf.yumvar['arch']
        msg += "  basearch: %s\n" % self.conf.yumvar['basearch']
        msg += "  releasever: %s\n" % self.conf.yumvar['releasever']
        msg += "  yum ver: %s\n" % yum.__version__
        msg += "  enabled plugins: %s\n" % ",".join(self.plugins._plugins.keys())
        msg += "  global excludes: %s\n" % ",".join(self.conf.exclude)
        return msg

    def dump_rpm_problems(self):

        pkgs = {}
        for po in self.rpmdb.returnPackages():
            tup = po.pkgtup
            header = po.hdr
            requires = zip(
                header[rpm.RPMTAG_REQUIRENAME],
                header[rpm.RPMTAG_REQUIREFLAGS],
                header[rpm.RPMTAG_REQUIREVERSION],
                )
            pkgs[tup] = requires


        errors = []
        providers = {} # To speed depsolving, don't recheck deps that have
                       # already been checked
        provsomething = {}
        for (pkg,reqs) in pkgs.items():
            for (req,flags,ver)  in reqs:
                if ver == '':
                    ver = None
                rflags = flags & 15
                if req.startswith('rpmlib'): 
                    continue # ignore rpmlib deps

                if not providers.has_key((req,rflags,ver)):
                    resolve_sack = self.rpmdb.whatProvides(req,rflags,ver)
                else:
                    resolve_sack = providers[(req,rflags,ver)]

                if len(resolve_sack) < 1:
                    errors.append("Package %s requires %s" % (pkg[0],
                      miscutils.formatRequire(req,ver,rflags)))
                else:
                    for rpkg in resolve_sack:
                        # Skip packages that provide something for themselves
                        # as these can still be leaves
                        if rpkg != pkg:
                            provsomething[rpkg] = 1
                    # Store the resolve_sack so that we can re-use it if another
                    # package has the same requirement
                    providers[(req,rflags,ver)] = resolve_sack


        msg = "%%%%RPMDB PROBLEMS\n"
        for error in errors:
            msg += "%s\n" % error

        # possibly list all verify failures, too
        return msg



    def create_debug_file(self, fn=None):
        """create debug txt file and compress it, place it at yum_debug_dump.txt.gz
           unless fn is specified"""
        if not fn:
            fn = 'yum_debug_dump.txt.gz'

        if not fn.startswith('/'):
            fn = '%s/%s' % (os.getcwd(), fn)

        fo = gzip.GzipFile(fn, 'w')

        msg = "yum-debug-dump version %s\n" % self.file_version
        fo.write(msg)
        fo.write(self.dump_system_info())
        fo.write(self.dump_yum_config_info())
        fo.write(self.dump_rpm_problems())
        fo.write(self.dump_rpmdb())
        if not self.opts.norepos:
            fo.write(self.dump_repos())
        fo.close()
        return fn

def main():
    my = YumDebugDump()
    my.doConfigSetup(init_plugins=True)
    fn = my.create_debug_file()
    print "Output written to: %s" % fn

if __name__ == "__main__":
    main()



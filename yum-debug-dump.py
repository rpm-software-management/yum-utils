#!/usr/bin/python -tt

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
## (c) 2008 Red Hat. Written by skvidal@fedoraproject.org

import os
import subprocess
import sys
import time
import yum
from yum import Errors
from yum.misc import getCacheDir
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
        parser.set_usage("yum-debug-dump [options] [filename]")
        parser.add_option("--norepos", action="store_true", default=False,
           help="do not attempt to dump the repository contents")
        self.opts, self.args = parser.parse_args()

    def dump_rpmdb(self):
        msg = "%%%%RPMDB\n"
        for po in sorted(self.rpmdb):
            msg += '  %s:%s-%s-%s.%s\n' % (po.epoch, po.name, po.ver,po.rel, po.arch)

        return msg

    def dump_rpmdb_versions(self):
        msg = "%%%%RPMDB VERSIONS\n"
        # This should be the same as the default [yum] group in version-groups
        yumcore = set(['yum', 'rpm', 'yum-metadata-parser'])
        yumplus = set(['glibc', 'sqlite',
                       'libcurl', 'nss',
                       'rpm', 'rpm-libs', 'rpm-python',
                       'python',
                       'python-iniparse', 'python-urlgrabber', 'python-pycurl'])
        yumplus.update(yumcore)
        groups = {'yum-core' : yumcore,
                  'yum'      : yumplus}
        data = self.rpmdb.simpleVersion(False, groups=groups)
        msg += '  all: %s\n' % (data[0],)
        for grp in sorted(data[2]):
            msg += '  %s: %s\n' % (grp, data[2][grp])

        return msg

    def dump_repos(self):
        msg = "%%%%REPOS\n"

        # Set up the sacks first, to capture and log any broken repos.  We
        # cannot yet call returnPackages() from this loop as that would lead to
        # a KeyError if some repo got disabled by pkgSack due to
        # skip_if_unavailable=true in a previous iteration.
        #
        # A failure means remaining repos were not processed, so we have to
        # retry the whole process ourselves by calling pkgSack again.  Since
        # the worst case scenario is that all the repos are broken, we have to
        # do this at least as many times as there are enabled repos.
        for repo in sorted(self.repos.listEnabled()):
            try:
                self.pkgSack
            except Errors.RepoError, e:
                msg += "Error accessing repo %s: %s\n" % (e.repo, str(e))
                self.repos.disableRepo(e.repo.id)
            else:
                break

        # Dump the packages now
        for repo in sorted(self.repos.listEnabled()):
            try:
                msg += '%%%s - %s\n' % (repo.id, repo.urls[0])
                msg += "  excludes: %s\n" % ",".join(repo.exclude)
                for po in sorted(self.pkgSack.returnPackages(repo.id)):
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

# remove pylint false positive
# Instance of 'DummyYumPlugins' has no '_plugins' member (but some types could not be inferred)
# pylint: disable-msg=E1103
    def dump_yum_config_info(self):
        msg = "%%%%YUM INFO\n"
        msg += "  arch: %s\n" % self.conf.yumvar['arch']
        msg += "  basearch: %s\n" % self.conf.yumvar['basearch']
        msg += "  releasever: %s\n" % self.conf.yumvar['releasever']
        msg += "  yum ver: %s\n" % yum.__version__
        msg += "  enabled plugins: %s\n" % ",".join(self.plugins._plugins.keys())
        msg += "  global excludes: %s\n" % ",".join(self.conf.exclude)
        return msg
# pylint: enable-msg=E1103

    # FIXME: This should use rpmdb.check_*()
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
        for (pkg,reqs) in sorted(pkgs.items()):
            for (req,flags,ver)  in reqs:
                if ver == '':
                    ver = None
                rflags = flags & 15
                if req.startswith('rpmlib'): 
                    continue # ignore rpmlib deps

                if (req,rflags,ver) not in providers:
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
            now = time.strftime("%Y-%m-%d_%T", time.localtime(time.time()))
            fn = 'yum_debug_dump-%s-%s.txt.gz' % (os.uname()[1], now)

        if not fn.startswith('/'):
            fn = '%s/%s' % (os.getcwd(), fn)

        if fn.endswith('.gz'):
            fo = gzip.GzipFile(fn, 'w')
        else:
            fo = open(fn, 'w')

        msg = "yum-debug-dump version %s\n" % self.file_version
        fo.write(msg)
        fo.write(self.dump_system_info())
        fo.write(self.dump_yum_config_info())
        fo.write(self.dump_rpm_problems())
        fo.write(self.dump_rpmdb())
        if not self.opts.norepos:
            fo.write(self.dump_repos())
        fo.write(self.dump_rpmdb_versions())
        fo.close()
        return fn

def main():
    my = YumDebugDump()

    # make yum-debug-dump work as non root user.
    if my.conf.uid != 0:
        cachedir = getCacheDir()
        if cachedir is None:
            my.logger.error("Error: Could not make cachedir, exiting")
            sys.exit(50)
        my.repos.setCacheDir(cachedir)

        # Turn off cache
        my.conf.cache = 0
        # make sure the repos know about it, too
        my.repos.setCache(0)

    filename = None
    if my.args:
        filename = my.args[0]
    fn = my.create_debug_file(fn=filename)
    print "Output written to: %s" % fn

if __name__ == "__main__":
    main()

#!/usr/bin/python

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
#
# Copyright Red Hat Inc. 2007, 2008
#
# Author: James Antill <james@fedoraproject.com>
# Examples:
#
# yum --tmprepo=http://example.com/foo/bar.repo ...

from yum.plugins import TYPE_INTERACTIVE
import logging # for commands

import urlgrabber.grabber
import tempfile
import os
import shutil
import time

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)

def make_validate(log, pkgs_gpgcheck, repo_gpgcheck):
    def tvalidate(repo):
        if pkgs_gpgcheck or repo_gpgcheck:

            # Don't ever allow them to set gpgcheck='false'
            if pkgs_gpgcheck and not repo.gpgcheck:
                log.warn("Repo %s tried to set gpgcheck=false" % repo)
                return False

            if (repo_gpgcheck and hasattr(repo, 'repo_gpgcheck') and
                not repo.repo_gpgcheck):
                log.warn("Repo %s tried to set repo_gpgcheck=false" % repo)
                return False

            # Don't allow them to set gpgkey=anything
            for key in repo.gpgkey:
                if not key.startswith('file:/'):
                    log.warn("Repo %s tried to set gpgkey to %s" %
                             (repo, repo.gpgkey))
                    return False

        return True

    return tvalidate

dnames = []
class AutoCleanupDir:
    """
    Given a directory ... let it exist until "the end", and then clean it up.
    """

    def __init__(self, dname):
        self.dname = dname
        # Want it to live until python shutdown
        dnames.append(self)

    # Can't use __del__ as python doesn't dtrt. on exit
    def cleanup(self):
        shutil.rmtree(self.dname, ignore_errors=True)

def close_hook(conduit):
    global dnames
    for dname in dnames:
        dname.cleanup()
    dnames = []

def add_dir_repo(base, trepo, cleanup):
    # Let people do it via. local directories ... we don't want this for
    # HTTP because people _should_ just generate .repo files, but for
    # local CDs of pkgs etc. we'll be nice.
    trepo_path = trepo[len("file:"):]
    trepo_data = tempfile.mkdtemp()
    if cleanup:
        AutoCleanupDir(trepo_data)
    else:
        os.chmod(trepo_data, 0755)
    trepo_name = os.path.basename(os.path.dirname(trepo_path))
    tmp_fname  = "%s/tmp-%s.repo" % (trepo_data, trepo_name)
    repoid     = "T-%0.4s-%x" % (trepo_name, int(time.time()))
    tpc = 'true'
    if not lpgpgcheck:
        tpc = 'false'
    trc = 'true'
    if not lrgpgcheck:
        trc = 'false'
    open(tmp_fname, "wb").write("""\
[%(repoid)s]
name=Tmp. repo. for %(path)s
baseurl=file:%(dname)s
enabled=1
gpgcheck=%(pkgs_gpgcheck)s
repo_gpgcheck=%(repo_gpgcheck)s
metadata_expire=0
#  Make cost smaller, as we know it's "local" ... if this isn't good just create
# your own .repo file. ... then you won't need to createrepo each run either.
cost=500
""" % {'path'     : trepo_path,
       'repoid'   : repoid,
       'dname'    : trepo_data,
       'pkgs_gpgcheck' : tpc,
       'repo_gpgcheck' : trc,
       })
    if cleanup:
        print "Creating tmp. repodata for:", trepo_path
    else:
        print "Creating saved repodata for:", trepo_path
        print "    * Result is saved here :", tmp_fname
        
    os.spawnlp(os.P_WAIT, "createrepo",
               "createrepo", "--database", "--baseurl", trepo,
               "--outputdir", trepo_data, trepo_path)
    AutoCleanupDir("%s/%s" % (base.conf.cachedir, repoid))
    return tmp_fname

def add_repomd_repo(base, repomd):
    # Let people do it via. poitning at the repomd.xml file ... smeg it
    trepo_data = tempfile.mkdtemp()
    AutoCleanupDir(trepo_data)
    trepo_name = os.path.basename(os.path.dirname(os.path.dirname(repomd)))
    tmp_fname  = "%s/tmp-%s.repo" % (trepo_data, trepo_name)
    repoid     = "T-%0.4s-%x" % (trepo_name, int(time.time()))
    pgpgcheck, rgpgcheck = rpgpgcheck, rrgpgcheck
    if repomd.startswith("file:"):
        pgpgcheck, rgpgcheck = lpgpgcheck, lrgpgcheck
    tpc = 'true'
    if not pgpgcheck:
        tpc = 'false'
    trc = 'true'
    if not rgpgcheck:
        trc = 'false'
    open(tmp_fname, "wb").write("""\
[%(repoid)s]
name=Tmp. repo. for %(path)s
baseurl=%(dname)s
enabled=1
gpgcheck=%(pkgs_gpgcheck)s
repo_gpgcheck=%(repo_gpgcheck)s
metadata_expire=0
""" % {'path'     : repomd,
       'repoid'   : repoid,
       'dname'    : repomd[:-len("repodata/repomd.xml")],
       'pkgs_gpgcheck' : tpc,
       'repo_gpgcheck' : trc,
       })
    print "Creating tmp. repo for:", repomd
    AutoCleanupDir("%s/%s" % (base.conf.cachedir, repoid))
    return tmp_fname

# Note that mirrorlist also includes metalink, due to the anaconda hack.
def add_mirrorlist_repo(base, mirrorlist):
    # Let people do it via. poitning at the repomd.xml file ... smeg it
    trepo_data = tempfile.mkdtemp()
    AutoCleanupDir(trepo_data)
    trepo_name = os.path.basename(mirrorlist)
    tmp_fname  = "%s/tmp-%s.repo" % (trepo_data, trepo_name)
    repoid     = "T-%4.4s-%x" % (trepo_name, int(time.time()))
    tpc = 'true'
    if not rpgpgcheck:
        tpc = 'false'
    trc = 'true'
    if not rrgpgcheck:
        trc = 'false'
    open(tmp_fname, "wb").write("""\
[%(repoid)s]
name=Tmp. repo. for %(path)s
mirrorlist=%(dname)s
enabled=1
gpgcheck=true
metadata_expire=0
""" % {'path'     : mirrorlist,
       'repoid'   : repoid,
       'dname'    : mirrorlist,
       'pkgs_gpgcheck' : tpc,
       'repo_gpgcheck' : trc,
       })
    print "Creating tmp. repo for:", mirrorlist
    AutoCleanupDir("%s/%s" % (base.conf.cachedir, repoid))
    return tmp_fname

def add_repos(base, log, tmp_repos, tvalidate, tlocvalidate, cleanup_dir_temp,
              nogpgcheck):
    """ Add temporary repos to yum. """
    # Don't use self._splitArg()? ... or require URLs without commas?
    for trepo in tmp_repos:
        if trepo.startswith("~/"):
            trepo = "%s%s" % (os.environ['HOME'], trepo[1:])
        if trepo.startswith("/"):
            trepo = "file:%s" % trepo
        validate = tvalidate
        if trepo.startswith("file:"):
            validate = tlocvalidate
        if trepo.startswith("file:") and trepo.endswith("/"):
            if not os.path.isdir(trepo[len("file:"):]):
                log.warn("Failed to find directory " + trepo[len("file:"):])
                continue
            fname = add_dir_repo(base, trepo, cleanup_dir_temp)
        elif trepo.endswith("repodata/repomd.xml"):
            fname = add_repomd_repo(base, trepo)
        elif trepo.endswith(".repo"):
            grab = urlgrabber.grabber.URLGrabber()
            # Need to keep alive until fname is used
            gc_keep = tempfile.NamedTemporaryFile()
            fname = gc_keep.name
            try:
                fname = grab.urlgrab(trepo, fname)
            except urlgrabber.grabber.URLGrabError, e:
                log.warn("Failed to retrieve " + trepo)
                continue
        else:
            fname = add_mirrorlist_repo(base, trepo)

        base.getReposFromConfigFile(fname, validate=validate)

    if nogpgcheck:
        for repo in base.repos.listEnabled():
            repo.gpgcheck      = False
            repo.repo_gpgcheck = False
    # Just do it all again...
    base.setupProgressCallbacks()

rpgpgcheck = True  # Remote 
rrgpgcheck = False # Remote 
lpgpgcheck = True
lrgpgcheck = False
def_tmp_repos_cleanup = False

def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Add the --tmprepo option.
    '''
    global rpgpgcheck
    global rrgpgcheck
    global lpgpgcheck
    global lrgpgcheck
    global def_tmp_repos_cleanup
    
    parser = conduit.getOptParser()
    if not parser:
        return

    if hasattr(parser, 'plugin_option_group'):
        parser = parser.plugin_option_group

    parser.add_option("--tmprepo", action='append',
                      type='string', dest='tmp_repos', default=[],
                      help="enable one or more repositories from URLs",
                      metavar='[url]')
    parser.add_option("--tmprepo-keep-created", action='store_true',
                      dest='tmp_repos_cleanup', default=False,
                      help="keep created direcotry based tmp. repos.")
    #  We don't default to repository checks for repo files, because no one does
    # that signing.
    rpgpgcheck = conduit.confBool('main', 'pkgs_gpgcheck', default=True)
    rrgpgcheck = conduit.confBool('main', 'repo_gpgcheck', default=False)
    lpgpgcheck = conduit.confBool('main', 'pkgs_local_gpgcheck',
                                  default=rpgpgcheck)
    lrgpgcheck = conduit.confBool('main', 'repo_local_gpgcheck',
                                  default=False)
    def_tmp_repos_cleanup = conduit.confBool('main', 'cleanup', default=False)

_tmprepo_done = False
def prereposetup_hook(conduit):
    '''
    Process the tmp repos from --tmprepos.
    '''

    # Stupid group commands doing the explicit setup stuff...
    global _tmprepo_done
    if _tmprepo_done: return
    _tmprepo_done = True

    opts, args = conduit.getCmdLine()
    if not opts.tmp_repos:
        return

    if hasattr(conduit, 'registerPackageName'):
        conduit.registerPackageName("yum-plugin-tmprepo")

    log = logging.getLogger("yum.verbose.main")
    add_repos(conduit._base, log, opts.tmp_repos,
              make_validate(log, rpgpgcheck, rrgpgcheck),
              make_validate(log, lpgpgcheck, lrgpgcheck),
              not (opts.tmp_repos_cleanup or def_tmp_repos_cleanup),
              opts.nogpgcheck)

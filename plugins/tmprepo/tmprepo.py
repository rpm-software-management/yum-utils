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

import yum
import types
from yum.plugins import TYPE_INTERACTIVE
import logging # for commands
from yum import logginglevels

import logging
import urlgrabber.grabber
import tempfile
import os
import shutil

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)

def make_validate(log, gpgcheck):
    def tvalidate(repo):
        if gpgcheck:
    
            # Don't allow them to set gpgcheck=False
            if not repo.gpgcheck:
                log.warn("Repo %s tried to set gpgcheck=false" % repo)
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

def add_dir_repo(base, tmp_fname, trepo, log):
    # Let people do it via. local directories ... we don't want this for
    # HTTP because people _should_ just generate .repo files, but for
    # local CDs of pkgs etc. we'll be nice.
    trepo_path = trepo[len("file:"):]
    trepo_data = AutoCleanupDir(tempfile.mkdtemp())
    trepo_name = os.path.basename(os.path.dirname(trepo_path))
    open(tmp_fname, "wb").write("""\
[%(basename)s]
name=Temp. for %(rbasename)s
baseurl=file:%(dname)s
enabled=1
gpgcheck=1
metadata_expire=0
#  Make cost smaller, as we know it's "local" ... if this isn't good just create
# your own .repo file. ... then you won't need to createrepo each run either.
cost=500
""" % {'basename'  : os.path.basename(tmp_fname),
       'rbasename' : os.path.basename(trepo_name),
       'dname'     : trepo_data.dname})
    print "Creating repodata for directory:", os.path.basename(trepo_name)
    os.spawnlp(os.P_WAIT, "createrepo", "createrepo", "--baseurl", trepo,
               "--outputdir", trepo_data.dname, trepo_path)
    AutoCleanupDir("%s/%s" % (base.conf.cachedir, os.path.basename(tmp_fname)))

def add_repos(base, log, tmp_repos, tvalidate):
    """ Add temporary repos to yum. """
    # Don't use self._splitArg()? ... or require URLs without commas?
    for trepo in tmp_repos:
        tfo   = tempfile.NamedTemporaryFile()
        fname = tfo.name
        if trepo.startswith("/"):
            trepo = "file:%s" % trepo
        if trepo.startswith("file:") and trepo.endswith("/"):
            if not os.path.isdir(trepo[len("file:"):]):
                log.warn("Failed to find directory " + trepo[len("file:"):])
                continue
            add_dir_repo(base, fname, trepo)
        else:
            grab = urlgrabber.grabber.URLGrabber()
            try:
                grab.urlgrab(trepo, fname)
            except urlgrabber.grabber.URLGrabError, e:
                log.warn("Failed to retrieve " + trepo)
                continue

        base.getReposFromConfigFile(fname, validate=tvalidate)
        added = True

    # Just do it all again...
    base.setupProgressCallbacks()

my_gpgcheck = True
def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Add the --tmprepo option.
    '''
    global my_gpgcheck
    
    parser = conduit.getOptParser()
    if not parser:
        return

    parser.values.tmp_repos = []
    parser.add_option("--tmprepo", action='append',
                      type='string', dest='tmp_repos', default=[],
                      help="enable one or more repositories from URLs",
                      metavar='[url]')
    my_gpgcheck = conduit.confBool('main', 'gpgcheck', default=True)

def prereposetup_hook(conduit):
    '''
    Process the tmp repos from --tmprepos.
    '''

    opts, args = conduit.getCmdLine()
    if not opts.tmp_repos:
        return
    log = logging.getLogger("yum.verbose.main")
    add_repos(conduit._base, log, opts.tmp_repos,
              make_validate(log, my_gpgcheck))

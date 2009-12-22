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

# Copyright 2009 Red Hat, Inc
# written by Josef Bacik <josef@toxicpanda.com>

"""
This plugin creates a snapshot before any yum update or yum remove operation on
any btrfs filesystem that is affected by the update/remove operation.

This is a giant hammer.  Please be aware that if you rollback to a previous
snapshot that any other changes that occured to the filesystem after the
snapshot takes place will not be in the snapshot.  You of course can mount the
newer version elsewhere and copy the new versions of the files back to your
rolled-back snapshot.  You have been warned.
"""

from yum.plugins import TYPE_CORE
from yum.constants import *
import os
import sys
import time
from subprocess import Popen,PIPE

requires_api_version = '2.4'
plugin_type = (TYPE_CORE,)

def pretrans_hook(conduit):
    """
    This runs before the transaction starts.  Try to snapshot anything and
    everything that is snapshottable, since we do not know what an RPM will
    modify (thank you scriptlets).
    """
    if not os.path.exists("/etc/mtab"):
        conduit.info(1, "fs-snapshot: could not open /etc/mtab")
        pass

    excludeList = conduit.confString('main', 'exclude', default="").split()

    try:
        mtabfile = open('/etc/mtab', 'r')
        for line in mtabfile.readlines():
            device, mntpnt, type, rest  = line.split(' ', 3)

            # skip bind mounts
            if not rest.find("bind") == -1:
                continue

            skip = False
            for pnt in excludeList:
                if pnt == mntpnt:
                    skip = True
                    break

            if skip:
                continue

            rc = _create_snapshot(device, mntpnt, type, conduit)
            if rc == 1:
                conduit.info(1, "fs-snapshot: error snapshotting " + mntpnt)
        mtabfile.close()
    except Exception as (errno, strerror):
        conduit.info(1, "fs-snapshot: error reading /etc/mtab")
    pass

def _create_snapshot(device, mntpnt, type, conduit):
    """
    Determines if the device is capable of being snapshotted and then calls the
    appropriate snapshotting function.  The idea is you could add something for
    lvm snapshots, nilfs2 or whatever else here.
    """

    # at some point it would be nice to add filtering here, so users can specify
    # which filesystems they don't want snapshotted and we'd automatically match
    # them here and just return.

    if type == "btrfs":
        return _create_btrfs_snapshot(mntpnt, conduit)
    
    return 0

def _create_btrfs_snapshot(dir, conduit):
    """
    Runs the commands necessary for a snapshot.  Basically its just

    btrfsctl -c /dir/to/snapshot    #this syncs the fs
    btrfsctl -s /dir/to/snapshot/yum-month-date-year-hour:minute
                /dir/to/snapshot

    and then we're done.
    """

    #/etc/mtab doesn't have /'s at the end of the mount point, unless of course
    #the mountpoint is /
    if not dir.endswith("/"):
        dir = dir + "/"

    snapname = dir + "yum-" + time.strftime("%m-%d-%y-%H:%M")
    conduit.info(1, "fs-snapshot: snapshotting " + dir + ": " + snapname)
    p = Popen(["btrfsctl", "-c", dir], stdout=PIPE, stderr=PIPE)
    err = p.wait()
    if err:
        return 1
    p = Popen(["btrfsctl", "-s", snapname, dir], stdout=PIPE, stderr=PIPE)
    err = p.wait()
    if err:
        return 1
    return 0

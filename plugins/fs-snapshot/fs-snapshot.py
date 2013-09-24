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

# Copyright 2009-2010 Red Hat, Inc
# written by Josef Bacik <josef@toxicpanda.com>
#            Mike Snitzer <msnitzer@fedoraproject.org>

"""
This plugin creates a snapshot before any yum update or yum remove operation on
any btrfs filesystem that is affected by the update/remove operation.

This is a giant hammer.  Please be aware that if you rollback to a previous
snapshot that any other changes that occurred to the filesystem after the
snapshot takes place will not be in the snapshot.  You of course can mount the
newer version elsewhere and copy the new versions of the files back to your
rolled-back snapshot.  You have been warned.
"""

from yum.plugins import TYPE_CORE, PluginYumExit
from yum.constants import *
import yum.misc
import os
import time
from subprocess import Popen,PIPE

requires_api_version = '2.4'
plugin_type = (TYPE_CORE,)

# Globals
lvm_key = "create_lvm_snapshot"
# avoid multiple snapshot-merge checks via inspect_volume_lvm()
dm_snapshot_merge_checked = 0
dm_snapshot_merge_support = 0

def _fail(msg):
    raise PluginYumExit(msg)

def kernel_supports_dm_snapshot_merge():
    # verify the kernel provides the 'snapshot-merge' DM target
    # - modprobe dm-snapshot; dmsetup targets | grep -q snapshot-merge
    global dm_snapshot_merge_checked, dm_snapshot_merge_support
    if dm_snapshot_merge_checked:
        return dm_snapshot_merge_support
    os.system("modprobe dm-snapshot")
    p = Popen(["/sbin/dmsetup", "targets"], stdout=PIPE, stderr=PIPE)
    err = p.wait()
    if not err:
        output = p.communicate()[0]
        if not output.find("snapshot-merge") == -1:
            dm_snapshot_merge_support = 1
        dm_snapshot_merge_checked = 1
    return dm_snapshot_merge_support

def is_thin_volume(volume):
    return volume["segtype"] == "thin"

def inspect_volume_lvm(conduit, volume):
    """
    If volume is an LVM logical volume:
    - translate /dev/mapper name for LVM command use
    - conditionally establish lvm_key in volume
    """
    lvm_support = conduit.confBool('lvm', 'enabled', default=0)
    if not lvm_support:
        return 1
    device = volume["device"]
    # Inspect DM and LVM devices
    if device.startswith("/dev/dm-"):
        conduit.info(2, "fs-snapshot: unable to snapshot DM device: " + device)
        return 0
    if device.startswith("/dev/mapper/"):
        # convert /dev/mapper name to /dev/vg/lv for use with LVM2 tools
        # - 'dmsetup splitname' will collapse any escaped characters
        p = Popen(["/sbin/dmsetup", "splitname", "--separator", " ",
                   "--noheadings", "-c",
                   device], stdout=PIPE, stderr=PIPE)
        err = p.wait()
        if err:
            return 0
        output = p.communicate()[0]
        device = "/".join(output.split()[:2])
        device = device.replace("/dev/mapper/", "/dev/")
        volume["device"] = device

    # Check if device is managed by lvm
    # - FIXME filter out snapshot (and other) LVs; for now just rely
    #   on 'lvcreate' to prevent snapshots of unsupported LV types
    p = Popen(["/sbin/lvs", "--noheadings", "-o", "segtype", device], stdout=PIPE, stderr=PIPE)
    err = p.wait()
    if not err:
        volume["segtype"] = p.communicate()[0].strip()

        # FIXME allow creating snapshot LVs even if kernel doesn't
        # support snapshot-merge based system rollback? make configurable?
        if not is_thin_volume(volume) and not kernel_supports_dm_snapshot_merge():
            conduit.error(1, "fs-snapshot: skipping volume: %s, "
                          "kernel doesn't support snapshot-merge" % device)
            return 0
        volume[lvm_key] = 1
    return 1

def inspect_volume(conduit, volume):
    """
    Hook to check/filter volume for special characteristics.
    Returns 0 if volume failed inspection, otherwise 1.
    All inspect_volume_* methods act as filters; if they
    return 0 that means this volume failed inspection.
    """
    if not inspect_volume_lvm(conduit, volume):
        return 0
    # Additional inspect_volume_* methods may prove unnecessary but the
    # filtering nature of these methods would make them unavoidable; e.g.
    # just because a volume is LVM doesn't mean other filters should
    # be short-circuited
    return 1

def get_volumes(conduit):
    """
    Return all volumes that may be snapshotted.
    Each volume is a dictionary that contains descriptive key=value
    pairs.  All volumes will have 'device', 'mntpnt', and 'fstype'
    keys.  Extra keys may be established as a side-effect of
    inspect_volume().
    """
    # FIXME may look to return dictionary of volume dictionaries to
    # allow a volume to be looked up using its path (as the key).
    # - when a kernel package is being installed: could prove useful to check
    #   if "/" is an LVM volume and "/boot" is not able to be snapshotted; if
    #   so warn user that "/boot" changes (e.g. grub's menu.lst) will need to
    #   be manually rolled back.
    volumes = []

    excluded_mntpnts = conduit.confString('main', 'exclude', default="").split()
    try:
        mtabfile = open('/etc/mtab', 'r')
        for line in mtabfile.readlines():
            device, mntpnt, fstype, rest = line.split(' ', 3)
            volume = { "device" : device,
                       "mntpnt" : mntpnt,
                       "fstype" : fstype }

            if mntpnt in excluded_mntpnts:
                continue

            # skip bind mounts
            if not rest.find("bind") == -1:
                continue

            # skip any mounts whose device doesn't have a leading /
            # - avoids proc, sysfs, devpts, sunrpc, none, etc.
            if not device.find("/") == 0:
                continue

            # skip volume if it doesn't pass inspection
            # - inspect_volume may create additional keys in this volume
            if not inspect_volume(conduit, volume):
                continue

            volumes.append(volume)

        mtabfile.close()

    except Exception, e:
        msg = "fs-snapshot: error processing mounted volumes: %s" % e
        _fail(msg)

    return volumes


def _create_snapshot(conduit, snapshot_tag, volume):
    """
    Determines if the device is capable of being snapshotted and then calls the
    appropriate snapshotting function.  The idea is you could add something for
    nilfs2 or whatever else here.

    Returns 0 if no snapshot was created, 1 if an error occurred,
    and 2 if a snapshot was created.
    """
    if volume["fstype"] == "btrfs":
        return _create_btrfs_snapshot(conduit, snapshot_tag, volume)
    elif lvm_key in volume:
        return _create_lvm_snapshot(conduit, snapshot_tag, volume)

    return 0

def _create_btrfs_snapshot(conduit, snapshot_tag, volume):
    """
    Runs the commands necessary for a snapshot.  Basically its just

    btrfs filesystem sync /dir/to/snapshot    #this syncs the fs
    btrfs subvolume snapshot /dir/to/snapshot /dir/to/snapshot/${snapshot_tag}

    and then we're done.
    """
    mntpnt = volume["mntpnt"]
    #/etc/mtab doesn't have /'s at the end of the mount point, unless of course
    #the mountpoint is /
    if not mntpnt.endswith("/"):
        mntpnt = mntpnt + "/"

    snapname = mntpnt + snapshot_tag
    conduit.info(1, "fs-snapshot: snapshotting " + mntpnt + ": " + snapname)
    p = Popen(["/sbin/btrfs", "filesystem", "sync", mntpnt], stdout=PIPE, stderr=PIPE)
    err = p.wait()
    if err:
        return 1
    p = Popen(["/sbin/btrfs", "subvolume", "snapshot", mntpnt, snapname], stdout=PIPE, stderr=PIPE)
    err = p.wait()
    if err:
        return 1
    return 2

def add_lvm_tag_to_snapshot(conduit, tag, snap_volume):
    p = Popen(["/sbin/lvchange", "--addtag", tag, snap_volume],
              stdout=PIPE, stderr=PIPE)
    err = p.wait()
    if err:
        conduit.error(1, "fs-snapshot: couldn't add tag to snapshot: %s" %
                      snap_volume)

def _create_lvm_snapshot(conduit, snapshot_tag, volume):
    """
    Create LVM snapshot LV and tag it with $snapshot_tag.
    - This assumes that the volume is an origin LV whose VG
      has enough free space to accommodate a snapshot LV.
    - Also assumes user has configured 'lvcreate_size_args'.
    """
    if not is_thin_volume(volume):
        lvcreate_size_args = conduit.confString('lvm', 'lvcreate_size_args',
                                                default=None)

        if not lvcreate_size_args:
            conduit.error(1, "fs-snapshot: 'lvcreate_size_args' was not provided "
                          "in the '[lvm]' section of the config file")
            return 1

        if not lvcreate_size_args.startswith("-L") and not lvcreate_size_args.startswith("-l"):
            conduit.error(1, "fs-snapshot: 'lvcreate_size_args' did not use -L or -l")
            return 1

    device = volume["device"]
    if device.count('/') != 3:
        return 1

    mntpnt = volume["mntpnt"]
    kern_inst = True # Default to saying it might be.
    ts = conduit._base.rpmdb.readOnlyTS()
    kern_pkgtup = yum.misc.get_running_kernel_pkgtup(ts)
    del ts
    if kern_pkgtup is not None:
        kern_inst = conduit.getTsInfo().matchNaevr(name=kern_pkgtup[0])
    #  We only warn about this if a kernel is being installed or removed. Note
    # that this doesn't show anything if you move from "kern-foo" to "kern-bar"
    # but yum doesn't know any more than "what is running now".
    if mntpnt == "/" and kern_inst:
        conduit.info(1, "fs-snapshot: WARNING: creating LVM snapshot of root LV.  If a kernel is\n"
                        "                      being altered /boot may need to be manually restored\n"
                        "                      in the event that a system rollback proves necessary.\n")

    snap_device = device + "_" + snapshot_tag
    snap_lvname = snap_device.split('/')[3]
    conduit.info(1, "fs-snapshot: snapshotting %s (%s): %s" %
                 (mntpnt, device, snap_lvname))
    # Create snapshot LV
    lvcreate_cmd = ["/sbin/lvcreate", "-s", "-n", snap_lvname]
    if not is_thin_volume(volume):
        lvcreate_cmd.extend(lvcreate_size_args.split())
    lvcreate_cmd.append(device)
    p = Popen(lvcreate_cmd, stdout=PIPE, stderr=PIPE)
    err = p.wait()
    if err:
        conduit.error(1, "fs-snapshot: failed command: %s\n%s" %
                      (" ".join(lvcreate_cmd), p.communicate()[1]))
        return 1
    # Add tag ($snapshot_tag) to snapshot LV
    # - should help facilitate merge of all snapshot LVs created
    #   by a yum transaction, e.g.: lvconvert --merge @snapshot_tag
    if add_lvm_tag_to_snapshot(conduit, snapshot_tag, snap_device):
        return 1
    if conduit._base.__plugin_fs_snapshot_post_snapshot_tag == snapshot_tag:
        # Add tag to allow other tools (e.g. snapper) to link pre
        # and post snapshot LVs together
        pre_snap_lv_name = "%s_%s" % (device, conduit._base.__plugin_fs_snapshot_pre_snapshot_tag)
        pre_snapshot_tag = "yum_fs_snapshot_pre_lv_name=" + pre_snap_lv_name
        if add_lvm_tag_to_snapshot(conduit, pre_snapshot_tag, snap_device):
            return 1
    return 2

def create_snapshots(conduit):
    """
    This runs before the transaction starts.  Try to snapshot anything and
    everything that is snapshottable, since we do not know what an RPM will
    modify (thank you scriptlets).
    """
    # common snapshot tag format: yum_${year}${month}${day}${hour}${minute}${sec}
    snapshot_tag = "yum_" + time.strftime("%Y%m%d%H%M%S")
    if not conduit._base.__plugin_fs_snapshot_pre_snapshot_tag:
        conduit._base.__plugin_fs_snapshot_pre_snapshot_tag = snapshot_tag
    else:
        conduit._base.__plugin_fs_snapshot_post_snapshot_tag = snapshot_tag

    volumes = get_volumes(conduit)
    for volume in volumes:
        rc = _create_snapshot(conduit, snapshot_tag, volume)
        if rc == 1:
            _fail("fs-snapshot: error snapshotting " + volume["mntpnt"])
        elif rc == 2 and hasattr(conduit, 'registerPackageName'):
            # A snapshot was successfully created
            conduit.registerPackageName("yum-plugin-fs-snapshot")

def pretrans_hook(conduit):
    conduit._base.__plugin_fs_snapshot_pre_snapshot_tag = None
    conduit._base.__plugin_fs_snapshot_post_snapshot_tag = None
    create_snapshots(conduit)

def posttrans_hook(conduit):
    create_snapshots_in_post = conduit.confBool('main', 'create_snapshots_in_post', default=0)
    if create_snapshots_in_post:
        create_snapshots(conduit)

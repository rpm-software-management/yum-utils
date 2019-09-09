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
# Copyright 2009 Red Hat Inc
# written by Seth Vidal

# look through list of running apps
# report any app which was updated after it was started
# (and therefore needs to be restarted)


# for each /proc/number-dir 
# get stat of create time on that dir
# open up smaps and search for all lines with 'fd:' in them
# take filename
# search for the package owning that file
# make a list of installtimes of all pkgs of the files the program has open
# sort the list
# if the dir create time is < the largest time on the installtimes list
# then output the pid and process cmdline as needing to be restarted

#TODO:
# maybe note deleted files which are not owned by any pkg but which an app
# is still using
# output userids, too?


import sys
import os
import yum
import yum.misc
import glob
import stat
from optparse import OptionParser
from yum.Errors import RepoError
sys.path.insert(0,'/usr/share/yum-cli')
import utils

# For which package updates we should recommend a reboot
# Taken from https://access.redhat.com/solutions/27943
REBOOTPKGS = ['kernel', 'glibc', 'linux-firmware', 'systemd', 'udev',
              'openssl-libs', 'gnutls', 'dbus']

def parseargs(args):
    usage = """
    needs-restarting: Report a list of process ids of programs that started 
                    running before they or some component they use were updated.
    """
    parser = OptionParser(usage=usage)
    
    parser.add_option("-u", "--useronly", default=False, action="store_true",
      help='show processes for my userid only')
    parser.add_option("-r", "--reboothint", default=False, action="store_true",
      help=('only report whether a full reboot is required (exit code 1) or '
            'not (exit code 0)'))
    parser.add_option("-s", "--services", default=False, action="store_true",
      help='list the affected systemd services only')
    
    (opts, args) = parser.parse_args(args)
    return (opts, args)


def return_running_pids(uid=None):
    mypid = os.getpid()
    pids = []
    for fn in glob.glob('/proc/[0123456789]*'):
        if mypid == os.path.basename(fn):
            continue

        if uid: # meaning we're not root and we've added -u
            if os.stat(fn)[stat.ST_UID] != uid:
                continue

        pids.append(os.path.basename(fn))
    return pids

def get_open_files(pid):
    files = []
    smaps = '/proc/%s/smaps' % pid
    try:
        with open(smaps, 'r') as maps_f:
            maps = maps_f.readlines()
    except (IOError, OSError), e:
        print >>sys.stderr, "Could not open %s" % smaps
        return files

    for line in maps:
        slash = line.find('/')
        if slash == -1 or line.find('00:') != -1: # if we don't have a '/' or if we fine 00: in the file then it's not _REALLY_ a file
            continue
        line = line.replace('\n', '')
        filename = line[slash:]
        filename = filename.split(';')[0]
        filename = filename.strip()
        if filename not in files:
            files.append(filename)
    return files

def get_service(pid):
    """Return the systemd service to which the process belongs.

    More details:
    http://0pointer.de/blog/projects/systemd-for-admins-2.html
    https://www.freedesktop.org/wiki/Software/systemd/FrequentlyAskedQuestions/
    """

    fname = '/proc/%s/cgroup' % pid
    try:
        with open(fname, 'r') as f:
            groups = f.readlines()
    except (IOError, OSError), e:
        print >>sys.stderr, "Could not open %s" % fname
        return None

    for line in groups:
        line = line.replace('\n', '')
        hid, hsub, cgroup = line.split(':')
        if hsub == 'name=systemd':
            name = cgroup.split('/')[-1]
            if name.endswith('.service'):
                return name
    return None

def main(args):
    (opts, args)  = parseargs(args)

    myuid = os.geteuid()
    if myuid and not opts.useronly:
        print >>sys.stderr, "Please run as root or with --useronly option"
        sys.exit(1)

    my = yum.YumBase()
    my.preconf.init_plugins=False
    if hasattr(my, 'setCacheDir'):
        my.setCacheDir()
    my.conf.cache = True
    
    boot_time = utils.get_boot_time()

    if opts.reboothint:
        needing_reboot = set()
        for pkg in my.rpmdb.searchNames(REBOOTPKGS):
            if float(pkg.installtime) > float(boot_time):
                needing_reboot.add(pkg)
        if needing_reboot:
            print 'Core libraries or services have been updated:'
            for pkg in needing_reboot:
                print '  %s ->' % pkg.name, pkg.printVer()
            print
            print 'Reboot is required to ensure that your system benefits',
            print 'from these updates.'
            print
            print 'More information:'
            print 'https://access.redhat.com/solutions/27943'
            return 1
        else:
            print 'No core libraries or services have been updated.'
            print 'Reboot is probably not necessary.'
            return 0

    needing_restart = set()
    for pid in return_running_pids(uid=myuid):
        try:
            pid_start = utils.get_process_time(int(pid), boot_time)['start_time']
        except (OSError, IOError), e:
            continue
        found_match = False
        for fn in get_open_files(pid):
            if found_match:
                break
            just_fn = fn.replace('(deleted)', '')
            just_fn = just_fn.strip()            
            bogon = False
            # if the file is in a pkg which has been updated since we started the pid - then it needs to be restarted            
            for pkg in my.rpmdb.searchFiles(just_fn):
                if float(pkg.installtime) > float(pid_start):
                    needing_restart.add(pid)
                    found_match = True
                    continue
                if just_fn in pkg.ghostlist:
                    bogon = True
                    break
            
            if bogon:
                continue

            # if the file is deleted 
            if fn.find('(deleted)') != -1: 
                # and it is from /*bin/* then it needs to be restarted 
                if yum.misc.re_primary_filename(just_fn):
                    needing_restart.add(pid)
                    found_match = True
                    continue

                # if the file is from an old ver of an installed pkg - then assume it was just updated but the 
                # new pkg doesn't have the same file names. Fabulous huh?!
                my.conf.cache = False
                for oldpkg in my.pkgSack.searchFiles(just_fn): # ghostfiles are always bogons
                    if just_fn in oldpkg.ghostlist:
                        continue
                    if my.rpmdb.installed(oldpkg.name):
                        needing_restart.add(pid)
                        found_match = True
                        break

           
            
    if opts.services:
        names = set([get_service(pid) for pid in needing_restart])
        for name in names:
            if name is not None:
                print name
        return 0

    for pid in needing_restart:
        try:
            cmdline = open('/proc/' +pid+ '/cmdline', 'r').read()
        except (OSError, IOError), e:
            print >>sys.stderr, "Couldn't access process information for %s: %s" % (pid, str(e))
            continue
        # proc cmdline is null-delimited so clean that up
        cmdline = cmdline.replace('\000', ' ')
        print '%s : %s' % (pid, cmdline)
        
    return 0
    
if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except RepoError, e:
        print >>sys.stderr, e
        sys.exit(1)

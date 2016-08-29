#
# Copyright (c) 2014-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the plugins/pkgtorrent directory of this source tree. An
# additional grant of patent rights can be found in the PATENTS file in the
# same directory.
#
from urlparse import urlsplit, urlunsplit
from yum.plugins import TYPE_CORE
from collections import defaultdict
from hashlib import sha1
import subprocess
import httplib
import urllib
import urllib2
import struct
import socket
import stat
import time
import traceback
import os

requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)
CONTENT_DISPOSITION_PREFIX = 'attachment; filename='
PROC = '/proc'
# a format for identifying pre-existing torrent processses using argv[0]
DOWNLOAD_PROCESS_FORMAT = 'yum_torrent_downloading_%s'
# the directory managed by this program. At one point I thought of making
# it configurable, but because this program can do cache cleanups of files
# it's too dangerous to expose by default.
TORRENTBASE = '/var/cache/yum_torrent'
service, client, options, complete = None, None, None, None
timeout_download, timeout_nullfile = None, None
timeout_seed_min, timeout_seed_max = None, None
timeout_cache = None

def show_waiting(conduit, torrentlogs):
    n = len(torrentlogs)
    if n == 0:
        conduit.info(2, 'Download complete.')
        return
    if n > 1:
        s = 's'
    else:
        s = ''
    conduit.info(2, 'Waiting on %d torrent%s.' % (n, s))

def init_hook(conduit):
    global service, client, options, complete
    global timeout_download, timeout_nullfile
    global timeout_seed_min, timeout_seed_max
    global timeout_cache

    service = conduit.confString(
        'main',
        'service',
        default='/yum/torrent_service',
    )
    client = conduit.confString('main', 'client')
    options = conduit.confString('main', 'options', default='')
    complete = conduit.confString(
        'main',
        'complete',
        default='Download complete',
    )
    timeout_download = conduit.confInt('timeouts', 'download', default=200)
    timeout_seed_min = conduit.confInt('timeouts', 'seed_min', default=900)
    timeout_seed_max = conduit.confInt('timeouts', 'seed_max', default=86400)
    timeout_nullfile = conduit.confInt('timeouts', 'nullfile', default=86400)
    timeout_cache = conduit.confInt('timeouts', 'cache', default=172800)
    if timeout_seed_max < timeout_seed_min:
        conduit.info(
            2,
            'Warning: Seed maximum time (%d) is less than the minimum (%d). '
            'Forcing the maximum to match the minimum.' % (
                timeout_seed_max,
                timeout_seed_min,
            )
        )
        timeout_seed_max = timeout_seed_min
    if timeout_cache < timeout_seed_max:
        conduit.info(
            2,
            'Warning: Cache directory cleanup timeout (%d) is less than the '
            'maximum seed time (%d). Setting the cache timeout to the maximum '
            'seed time so we do not delete files while we could be seeding '
            'them.' % (timeout_cache, timeout_seed_max),
        )
        timeout_cache = timeout_seed_max

def catchall(f):
    def inner(conduit):
        try:
            return f(conduit)
        except Exception as e:
            conduit.info(
                    2,
                    'Unhandled exception: %s Trace: %s' % (str(e),
                        traceback.format_exc()))
    return inner

@catchall
def predownload_hook(conduit):
    hostpaths = defaultdict(list)
    for package in conduit.getDownloadPackages():
        try:
            result = urlsplit(package.remote_url)
            if result.scheme not in ('http', 'https'):
                # whitelist http urls because we can POST to them. This will
                # disable the plugin for ftp and file protocols.
                continue
            # normal yum plugin passed objects with this member; note that
            # yum/sqlitesack.py overrides __getattr__ for this object with an
            # implementation that doesn't support default fallbacks, and throws
            # a KeyError exception when an invalid attribute is accessed; this
            # is why we have to do this dance.
            if hasattr(package, 'localpath'):
                localpath = getattr(package, 'localpath')
            else:
                # if not present, then we're running from Anaconda, which uses
                # yum.sqlitesack.YumAvailablePackageSqlite instances.
                localpath = package.localPkg()
            hostpaths[result.scheme, result.netloc].append((
                result.path,
                package.size,
                localpath,
            ))
        except ValueError:
            # urlsplit() will choke on localinstall packages. There isn't
            # a more elegant solution. In any case, if this code breaks, the
            # fallback is to download normally which is fine.
            pass

    # lame enumeration of process argv[0]. We used this later to work out if
    # we're already downloading said torrent.
    process_names = {}
    for pid in os.listdir(PROC):
        try:
            # We want to limit to only numeric directories, and we'll store
            # the number, not string later.
            process_names[
                open(os.path.join(PROC, pid, 'cmdline')).read().split('\0')[0]
            ] = pid
        except:
            # hey, we tried.
            pass

    torrentlogs = {}
    for (scheme, netloc), packages in hostpaths.iteritems():
        packages.sort()
        packagepaths = [p[0] for p in packages]
        digest = sha1('\n'.join(packagepaths)).hexdigest()
        url = urlunsplit(
            (scheme, netloc, service + '/digest/' + digest, '', '')
        )
        try:
            conduit.info(2, 'GET URL: %s' % (url,))
            res = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            if e.getcode() == 412:
                conduit.info(
                    2,
                    "Service doesn't know about this digest, POST'ing paths..."
                )
                data = urllib.urlencode([('p', p) for p in packagepaths])
                try:
                    res = urllib2.urlopen(url, data)
                except urllib2.HTTPError as e:
                    conduit.info(
                        2,
                        'Service failed %d, skipping torrent' % (e.getcode(),)
                    )
                    continue
                except (httplib.HTTPException, urllib2.URLError) as e:
                    conduit.info(
                        2,
                        'Service failed: %s, skipping torrent' % (str(e)))
                    continue
            else:
                conduit.info(
                    2,
                    "Server returned %d. Perhaps service isn't installed?" % (
                        e.getcode(),
                    ),
                )
                continue

        code = res.getcode()
        if code != 200:
            conduit.info(2, 'Torrent service returned %s' % (code,))
            continue
        h = res.info()
        cd = res.info()['Content-Disposition']
        assert cd.startswith(CONTENT_DISPOSITION_PREFIX)
        filename = os.path.basename(cd[len(CONTENT_DISPOSITION_PREFIX):])
        open(os.path.join(TORRENTBASE, filename), 'w').write(res.read())

        # work out the seed time. It's 1/x shaped and biased by
        # timeout_seed_min and timeout_seed_max, and is salted by the digest
        # of the files specified, so different sets of files will be seeded
        # by different hosts.
        f = sha1(socket.gethostname())
        f.update(digest)
        # this requires some explanation: The digest for a sha1 returns
        # 20 bytes. I want to turn this into a float between 0 and 1. To
        # do this, I take the first 4 bytes, convert them into an "standard"
        # (4 byte) unsigned int, then divide by the max unsigned int.
        shard = struct.unpack('=L', f.digest()[:4])[0] / 2.0 ** 32
        # the seed time is a curve from 0% of hosts doing the max timeout
        # to 100% of hosts doing the minimum timeout. See
        # https://fburl.com/yumtorrentcurve
        # for the shape. Instead of importing the math library, I'm raising to
        # the 0.5th power, which is the same thing.
        seed = timeout_seed_min + (timeout_seed_max - timeout_seed_min) * \
                (1 - (-(shard - 2) * shard) ** 0.5)

        # replace '{seed_time}' in options (if present) with the number of
        # seconds to seed for.
        args = options.replace('{seed_time}', str(int(seed))).split()
        log = os.path.join(TORRENTBASE, filename + '.log')
        process_name = DOWNLOAD_PROCESS_FORMAT % (filename,)
        if process_name in process_names and os.path.isfile(log):
            pid = process_names[process_name]
            conduit.info(
                2,
                'PID %s is downloading/seeding %s, not spawning new client.' % (
                    pid,
                    filename,
                )
            )
        else:
            subprocess.Popen(
                [process_name] + args + [filename],
                executable=client,
                stdout=open(log, 'w'),
                cwd=TORRENTBASE,
                close_fds=True,
            )

        # let's say all the files were last modified at the EPOCH which isn't
        # true but this means each will get completely read at startup.
        torrentlogs[open(log)] = ''

    download_until = time.time() + timeout_download
    # it's possible you end up with the complete message across loops. Keep
    # up to this much data from previous runs.
    extra_data_len = len(complete) - 1
    show_waiting(conduit, torrentlogs)
    while torrentlogs:
        # note we're modifying the torrentlogs dict but this is a copy.
        # this will need to be changed for python3
        for log, olddata in torrentlogs.items():
            # a single read() may not return everything so keep doing it
            # until you get nothing.
            data = [olddata]
            while True:
                # read alllllll the data
                moar = log.read()
                if moar == '':
                    # eof, that'll do.
                    break
                data.append(moar)
            data = ''.join(data)
            if data.find(complete) != -1:
                log.close()
                del torrentlogs[log]
                show_waiting(conduit, torrentlogs)
                continue
            # update the tail of data last seen.
            torrentlogs[log] = data[-extra_data_len:]

        if time.time() > download_until:
            conduit.info(
                2,
                'Timed out waiting for bittorent download completion. '
                'Falling back on normal download semantics.',
            )
            # let's just bail on everything. We can't reliably do any
            # symlinking or nullfile cleanup. Note we keep trying to
            # download into the yum_torrent directory and seed as normal.
            return
        # we can't use poll() so we'll pause for a moment for things to change.
        time.sleep(1)

    # note client can run longer than this, and should, so it keeps seeding.

    nulldir = os.path.join(TORRENTBASE, service[1:], 'nullfile')
    if os.path.isdir(nulldir):
        age_threshold = time.time() - timeout_nullfile
        for filename in os.listdir(nulldir):
            nullfile = os.path.join(nulldir, filename)
            s = os.stat(nullfile)
            if s.st_mtime < age_threshold:
                conduit.info(3, 'Deleting nullfile: %s' % (nullfile,))
                os.unlink(nullfile)
                continue
            # rough heuristic for spotting sparse files.
            if s.st_blocks > (s.st_blksize / 512):
                tmpnullfile = '%s.sparse' % (nullfile,)
                f = open(tmpnullfile, 'wb')
                f.seek(s.st_size - 1)
                f.write('\0')
                f.close()
                # atomically replace
                try:
                    os.rename(tmpnullfile, nullfile)
                except OSError:
                    os.unlink(tmpnullfile)

    cutoff = time.time() - timeout_cache
    for packages in hostpaths.itervalues():
        for name, size, localpath in packages:
            downloadpath = os.path.join(TORRENTBASE, name[1:])
            try:
                if os.stat(downloadpath).st_mtime < cutoff:
                    # This file was about to expire, but let's keep it
                    # alive as we just referenced it again.
                    os.utime(downloadpath, None)
            except OSError as e:
                if e.errno == 2:
                    # file not found. We can't touch it, and shouldn't link
                    # to it either.
                    conduit.info(
                        2,
                        'Warning: Download file not found: %s' % (downloadpath,)
                    )
                    continue
                raise

            if os.path.exists(localpath):
                continue
            localdir = os.path.dirname(localpath)
            if not os.path.isdir(localdir):
                os.makedirs(localdir)
            try:
                os.link(downloadpath, localpath)
            except OSError as e:
                if e.errno != 18:
                    # not a cross device hardlink error, can't handle this.
                    raise
                os.symlink(
                    os.path.relpath(downloadpath, localdir),
                    localpath,
                )

@catchall
def clean_hook(conduit):
    # Let's go look at all of TORRENTBASE and clean up files older than
    # timeout_cache and remove empty directories.
    cutoff = time.time() - timeout_cache
    for root, dirs, files in os.walk(TORRENTBASE, topdown=False):
        for name in files:
            fullpath = os.path.join(root, name)
            if os.stat(fullpath).st_mtime >= cutoff:
                continue
            # note this doesn't try to work out what is symlinked to this file.
            # On the unlikely event that we end up breaking a symlink, then
            # yum will download a file and replace the symlink with a real file.
            conduit.info(2, 'Deleting expired cache file: %s' % (fullpath,))
            os.unlink(fullpath)

            # TODO: also delete empty directories.
        for name in dirs:
            fullpath = os.path.join(root, name)
            if os.listdir(fullpath):
                continue
            conduit.info(2, 'Deleting empty directory: %s' % (fullpath,))
            os.rmdir(fullpath)

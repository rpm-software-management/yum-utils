#
# Copyright (c) 2014-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the plugins/pkgtorrent directory of this source tree. An
# additional grant of patent rights can be found in the PATENTS file in the
# same directory.
#
import os
import cgi
import cPickle as pickle
import time
import datetime
import locale
import glob

try:
    from hashlib import sha1
except ImportError:
    # fall back.
    from sha import new as sha1

# expires headers must be in en_US names, so set this once.
locale.setlocale(locale.LC_TIME, 'en_US')

# derived from https://gist.github.com/stendec/949007 by stendec365@gmail.com
# and released under the BSD license.
def bencode(o):
    if isinstance(o, unicode):
        o = o.encode('utf8')
    if isinstance(o, str):
        return '%d:%s' % (len(o), o)
    elif type(o) in (list, set, tuple):
        return 'l%se' % ''.join([bencode(x) for x in o])
    elif type(o) in (int, long):
        return 'i%se' % (o,)
    elif isinstance(o, dict):
        return 'd%se' % ''.join(
            ['%s%s' % (bencode(k), bencode(o[k])) for k in sorted(o.keys())]
        )

    raise TypeError('Cannot encode object of type, %s' % str(type(object)))

# if the pickle datastructures change, bump this to invalidate caches.
PROTOCOL = 4
CACHEROOT = '/var/cache/torrent_service'
PIECECACHE = os.path.join(CACHEROOT, 'pieces')
INFOCACHE = os.path.join(CACHEROOT, 'info')
INFOCACHEMAX = 3600  # number of seconds a given torrent is valid for
INFOCACHEWAIT = 25   # how long to wait for another process to create the info
TRACKERS_LIST_PATH = '/var/lib/torrent_service/trackers'
# number of seconds between stat'ing TRACKERS_LIST_PATH for change
TRACKERS_LIST_INTERVAL = 60
NULLPATH = '/nullfile/'
BLOCKSIZE = 2 ** 20  # 1MB should be enough for anybody.

if not os.path.exists(PIECECACHE):
    os.makedirs(PIECECACHE)
if not os.path.exists(INFOCACHE):
    os.makedirs(INFOCACHE)

def create_nullfile(path_info, start_response):
    size = path_info[len(NULLPATH):].split('_')[0]

    if int(size) > BLOCKSIZE:
        out = 'Refusing to create a nullfile bigger than server BLOCKSIZE'
        start_response('403 Forbidden', [
            ('Content-type', 'text/plain'),
            ('Content-Length', str(len(out))),
        ])
        return [out]

    start_response('200 OK', [
        ('Content-type', 'application/octet-stream'),
        ('Content-Transfer-Encoding', 'binary'),
        ('Content-Disposition', 'attachment;'),
        (
            'Expires',  # Not convinced this helps with caching
            (
                datetime.datetime.utcnow() + datetime.timedelta(days=1)
            ).strftime('%a, %d %b %Y %H:%M:%S GMT'),
        ),
        ('Content-Length', size),
    ])
    return ['\0' * int(size)]

# it expired at the epoch to start with.
trackers, trackers_expires, trackers_mtime = None, 0, 0
def update_trackers():
    global trackers, trackers_expires, trackers_mtime
    now = time.time()
    if trackers_expires > now:
        return
    trackers_expires = now + TRACKERS_LIST_INTERVAL
    if os.stat(TRACKERS_LIST_PATH).st_mtime == trackers_mtime:
        return
    trackers = open(TRACKERS_LIST_PATH).read().splitlines()

def create_torrent(environ, start_response):
    update_trackers()
    form = cgi.FieldStorage(
        fp=environ['wsgi.input'],
        environ=environ,
    )
    # support 3 different path specs:
    # /digest/{digest}
    # /single/path/to/file
    path_info = environ['PATH_INFO']
    # but let's make digest work first.
    if path_info.startswith('/digest/'):
        digest = os.path.basename(path_info[8:])
        pathspecs = form.getlist('p')
        single_mode = False
    elif path_info.startswith('/single/'):
        # pathspecs start with the leading / from single
        pathspecs = [path_info[7:]]
        digest = sha1('\n'.join(pathspecs)).hexdigest()
        single_mode = True
    log = environ['wsgi.errors']
    document_root = environ['DOCUMENT_ROOT']
    document_root_len = len(document_root)
    service_name = environ['SCRIPT_NAME'].split('/')[-1]

    paths = []
    if pathspecs:
        # build paths from possible wildcards
        for pathspec in pathspecs:
            if pathspec.endswith(os.pathsep + '**'):
                # rsync style, directory and all subdirectories
                raise NotImplementedError('You gotta write this')
            for p in glob.glob(os.path.join(document_root, pathspec[1:])):
                s = os.stat(p)
                paths.append((p[document_root_len:], s.st_mtime))
    single = single_mode and len(paths) == 1

    digestfile = os.path.join(INFOCACHE, digest)
    # look up a previously created torrent
    try:
        # single file torrents aren't padded and do not have leading directories
        # so should be cached using a slightly different filename
        if single:
            digestfile += '_s'
        digeststat = os.stat(digestfile)
        if digeststat.st_mtime < (time.time() - INFOCACHEMAX):
            # file is too old, could be changed
            os.unlink(digestfile)
            raise KeyError('Cached torrent is too old')

        if digeststat.st_size == 0:
            # another process should be creating this.
            # let's take the mtime of the file, add in INFOCACHEWAIT and
            # watch it for changes.
            waituntil = digeststat.st_mtime + INFOCACHEWAIT
            while True:
                # yuck, polling.
                time.sleep(1)
                digeststat = os.stat(digestfile)
                if digeststat.st_size > 0:
                    # yea, something got written, so let's use it. Note we
                    # expect the file to get replaced atomically (which we do)
                    break
                if time.time() > waituntil:
                    raise KeyError('Timed out waiting for other writer')

        data = pickle.load(open(digestfile))
        if data[0] != PROTOCOL:
            os.unlink(digestfile)
            raise KeyError('Cache protocol is too old')

        protocol, info, info_hash, cached_paths, url_list_suffix = data
        if paths and cached_paths != paths:
            raise KeyError('Path from cache do not match, rebuild')
        return return_torrent(
            environ,
            start_response,
            info,
            info_hash,
            url_list_suffix,
        )
    except (OSError, IOError, KeyError), e:
        log.write(str(e))
        if not pathspecs:
            # Would use 404 here, but our caching infra caches 404s
            # and totally ignores all the controls for it.
            start_response('412 Precondition failed', [
                ('Cache-Control', 'no-cache, no-store, must-revalidate'),
                ('Pragma', 'no-cache'),
                ('Expires', '0'),
            ])
            return []

    # if we get this far, we should have a list of pathspecs to compare
    # to the expected digest.
    assert sha1('\n'.join(pathspecs)).hexdigest() == digest

    # It's possible we get a storm of people suddenly asking for exactly the
    # same set of files, so make them block and return the cached one.
    open(digestfile, 'w').close()
    files = []
    pieces = []
    lookup = []
    n = 0
    prefixes = set()
    nullfile = None
    nullusage = {}
    for path, mtime in paths:
        # these always start with / as they're relative to the root
        path = path[1:]
        cachepath = os.path.join(PIECECACHE, path, str(BLOCKSIZE))
        splitpath = path.split(os.sep)
        prefixes.add(splitpath[0])

        valid_cache = False
        if os.path.exists(cachepath):
            try:
                data = pickle.load(open(cachepath))
                if data[0] == PROTOCOL:
                    protocol, size, blocks, tail, cached_mtime = data
                    valid_cache = protocol == PROTOCOL and cached_mtime == mtime
                    padding = BLOCKSIZE - (size % BLOCKSIZE)
                else:
                    valid_cache = False
            except NotImplementedError:
                # TODO: figure out pickle and file exceptions
                valid_cache = False
        if not valid_cache:
            fullpath = os.path.join(document_root, path)
            size, blocks, tail = os.stat(fullpath).st_size, [], None
            f = open(fullpath)
            for i in xrange(int(size / BLOCKSIZE)):
                m = sha1()
                lookup.append((len(files), f.tell()))
                m.update(f.read(BLOCKSIZE))
                blocks.append(m.digest())
            remainder = size % BLOCKSIZE
            if remainder:
                m = sha1()
                # read as much as we can left
                lookup.append((len(files), f.tell()))
                buffer = f.read()
                assert len(buffer) == remainder
                m.update(buffer)
                tail = m.digest()
                padding = BLOCKSIZE - remainder
                m.update('\0' * padding)
                blocks.append(m.digest())
            blocks = ''.join(blocks)
            f.close()
            cachedir = os.path.dirname(cachepath)
            if not os.path.exists(cachedir):
                os.makedirs(cachedir)
            pickle.dump(
                (PROTOCOL, size, blocks, tail, mtime),
                open(cachepath, 'wb'),
                pickle.HIGHEST_PROTOCOL,
            )
        # url-list requires a name, and that needs stripped
        # off all the paths inside the torrent to work.
        files.append({
            'path': splitpath[1:],
            'length': size,
        })
        if padding:
            n = nullusage.setdefault(padding, 0)
            name = '%d_%d' % (padding, n)
            nullusage[padding] = n + 1
            nullfile = {
                'path': [service_name, 'nullfile', name],
                'length': padding,
            }
            files.append(nullfile)
        pieces.append(''.join(blocks))

    try:
        assert len(prefixes) == 1
    except:
        log.write(repr(pieces))
        raise

    if files[-1] == nullfile:
        # we keep track of the last nullfile path spec we created in the loop.
        # the last file in the torrent doesn't need to be null padded.
        del files[-1]
        pieces[-1] = pieces[-1][:-len(tail)] + tail

    if single:
        url_list_suffix, name = os.path.split(path)
        info = {
            'name': name,
            'length': size,
        }
    else:
        url_list_suffix = ''
        info = {
            'name': list(prefixes)[0],
            'files': files,
        }
    info.update({
        'piece length': BLOCKSIZE,
        'pieces': ''.join(pieces),
    })
    info_hash = sha1(bencode(info)).hexdigest()

    tmpfile = '%s.tmp' % (digestfile,)
    pickle.dump(
        (PROTOCOL, info, info_hash, paths, url_list_suffix),
        open(tmpfile, 'wb'),
        pickle.HIGHEST_PROTOCOL
    )
    os.rename(tmpfile, digestfile)

    return return_torrent(
        environ,
        start_response,
        info,
        info_hash,
        url_list_suffix
    )

def return_torrent(environ, start_response, info, info_hash, url_list_suffix):
    # we want a list of trackers to put in the announce list that is salted by
    # the info_hash, so different info_hashes get distributed around different
    # primary trackers.
    announce = dict((sha1(t + info_hash).digest(), t) for t in trackers)
    announce_list = [[announce[k]] for k in sorted(announce.keys())]

    torrent = bencode({
        'url-list': [
            'http://%s/%s/' % (environ['HTTP_HOST'], url_list_suffix),
        ],
        'announce-list': announce_list,
        'info': info,
    })

    headers = [
        ('Content-type', 'application/x-bittorrent'),
        ('Content-Transfer-Encoding', 'binary'),
        ('Content-Disposition', 'attachment; filename=%s.torrent' % info_hash,),
        ('Content-Length', str(len(torrent))),
    ]
    start_response('200 OK', headers)
    return [torrent]

def application(environ, start_response):
    path_info = environ['PATH_INFO']
    if path_info.startswith(NULLPATH):
        return create_nullfile(path_info, start_response)
    return create_torrent(environ, start_response)

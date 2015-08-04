from yum.plugins import TYPE_CORE
from os import walk, path, fstat

requires_api_version = '2.3'
plugin_type = (TYPE_CORE,)
mtab = '/etc/mtab'
VERBOSE_DEBUGLEVEL = 3


def _stat_ino_fp(fp):
    """
    Get the inode number from file descriptor
    """
    return fstat(fp.fileno()).st_ino


def get_file_list(rpmpath):
    """
    Enumerate all files in a directory
    """
    for root, _, files in walk(rpmpath):
        for f in files:
            yield path.join(root, f)


def for_each_file(files, cb, m='rb'):
    """
    Open each file with mode specified in `m`
    and invoke `cb` on each of the file objects
    """
    if not files or not cb:
        return []
    ret = []
    for f in files:
        with open(f, m) as fp:
            ret.append(cb(fp))
    return ret


def do_detect_copy_up(files):
    """
    Open the files first R/O, then R/W and count unique
    inode numbers
    """
    num_files = len(files)
    lower = for_each_file(files, _stat_ino_fp, 'rb')
    upper = for_each_file(files, _stat_ino_fp, 'ab')
    diff = set(lower + upper)
    return len(diff) - num_files


def should_touch():
    """ 
    Touch the files only once we've verified that
    we're on overlay mount
    """
    if not path.exists(mtab):
        return False
    with open(mtab, 'r') as f:
        line = f.readline()
        return line.startswith('overlay / overlay')
    return False


def prereposetup_hook(conduit):
    if not should_touch():
        return

    rpmdb_path = conduit.getRpmDB()._rpmdbpath

    try:
        files = list(get_file_list(rpmdb_path))
        copied_num = do_detect_copy_up(files)
        conduit.info(VERBOSE_DEBUGLEVEL, "ovl: Copying up (%i) files from OverlayFS lower layer" % copied_num)
    except Exception as e:
        conduit.error(1, "ovl: Error while doing RPMdb copy-up:\n%s" % e)

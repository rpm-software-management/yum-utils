import time
from yum.packages import YumInstalledPackage
from rpmUtils.miscutils import splitFilename

requires_api_version = '2.1'

origpkgs = {}

# TODO: 
# - In posttrans we could get the changelogs from rpmdb thus avoiding
#   the costly 'otherdata' import but it would be nice to be able to present
#   the changelogs (optionally) *before* the y/n prompt and for that the import
#   would be needed anyway.
# - Add support to mail the changelogs to given address
# - Add cli-option for turning this on/off 

def changelog_delta(pkg, olddate):
    out = []
    for date, author, message in pkg.returnChangelog()[:5]:
        if date > olddate:
            out.append("* %s %s\n%s\n" % (time.ctime(int(date)), author, message))
    return out

def srpmname(pkg):
    n,v,r,e,a = splitFilename(pkg.returnSimple('sourcerpm'))
    return n

def postreposetup_hook(conduit):
    repos = conduit.getRepos()
    repos.populateSack(with='otherdata')

def pretrans_hook(conduit):
    # Find currently installed versions of packages we're about to update
    ts = conduit.getTsInfo()
    rpmdb = conduit.getRpmDB()
    for tsmem in ts.getMembers():
        for pkgtup in rpmdb.returnTupleByKeyword(name=tsmem.po.name, arch=tsmem.po.arch):
            for hdr in rpmdb.returnHeaderByTuple(pkgtup):
                # store the latest date in changelog entries
                times = hdr['changelogtime']
                n,v,r,e,a = splitFilename(hdr['sourcerpm'])
                origpkgs[n] = times[0]

def posttrans_hook(conduit):
    # Group by src.rpm name, not binary to avoid showing duplicate changelogs
    # for subpackages
    srpms = {}
    ts = conduit.getTsInfo()
    for tsmem in ts.getMembers():
        name = srpmname(tsmem.po)
        if srpms.has_key(name):
            srpms[name].append(tsmem.po)
        else:
            srpms[name] = [tsmem.po]

    conduit.info(2, "\nChanges in updated packages:\n")
    for name in srpms.keys():
        rpms = []
        if origpkgs.has_key(name):
            for rpm in srpms[name]:
                rpms.append("%s" % rpm)
            conduit.info(2, ", ".join(rpms))
            for line in changelog_delta(srpms[name][0], origpkgs[name]):
                conduit.info(2, line)

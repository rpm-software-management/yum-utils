#!/usr/bin/python -tt
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
# copyright (c) 2008 Red Hat, Inc - written by Seth Vidal and Will Woods

import yum
import sys
import os
from yum.misc import getCacheDir, checksum
import urlparse
from yum import Errors
from optparse import OptionParser
import ConfigParser

####
# take a file path to a repo as an option, verify all the metadata vs repomd.xml
# optionally go through packages and verify them vs the checksum in the primary

# Error values
BAD_REPOMD = 1
BAD_METADATA = 2
BAD_COMPS = 4
BAD_PACKAGES = 8
BAD_IMAGES = 16

# Testopia case/plan numbers
plan_number = 13
case_numbers = {'REPODATA': 56, 'CORE_PACKAGES': 57, 'COMPS': 58, 
                'BOOT_IMAGES': 59}

# URL for the RELAX NG schema for comps
SCHEMA='http://cvs.fedoraproject.org/viewcvs/*checkout*/comps/comps.rng'

def testopia_create_run(plan):
    '''Create a run of the given test plan. Returns the run ID.'''
    run_id = 49 # STUB actually create the run
    print "Testopia: created run %i of plan %i" % (run_id,plan)
    return run_id

def testopia_report(run,case,result):
    print "  testopia: reporting %s for case %s in run %i" % (result,
                                                              str(case),run)
    if type(case) == str:
        case = case_numbers[case]
    # STUB actually do the reporting

def checkfileurl(pkg):
    pkg_path = pkg.remote_url
    pkg_path = pkg_path.replace('file://', '')
    (csum_type, csum) = pkg.returnIdSum()
    
    try:
        filesum = checksum(csum_type, pkg_path)
    except Errors.MiscError:
        return False
    
    if filesum != csum:
        return False
    
    return True

def treeinfo_checksum(treeinfo):
    # read treeinfo file into cp
    # take checksums section
    cp = ConfigParser.ConfigParser()
    try:
        cp.read(treeinfo)
    except ConfigParser.MissingSectionHeaderError:
        # Generally this means we failed to access the file
        print "  could not find sections in treeinfo file %s" % treeinfo
        return
    except ConfigParser.Error:
        print "  could not parse treeinfo file %s" % treeinfo
        return
    
    if not cp.has_section('checksums'):
        print "  no checksums section in treeinfo file %s" % treeinfo
        return
    
    dir_path = os.path.dirname(treeinfo)
    for opt in cp.options('checksums'):

        fnpath = dir_path + '/%s' % opt
        fnpath = os.path.normpath(fnpath)
        csuminfo = cp.get('checksums', opt).split(':')
        if len(csuminfo) < 2:
            print "  checksum information doesn't make any sense for %s." % opt
            continue

        if not os.path.exists(fnpath):
            print "  cannot find file %s listed in treeinfo" % fnpath
            continue
        
        csum = checksum(csuminfo[0], fnpath)
        if csum != csuminfo[1]:
            print "  file %s %s does not match:\n   ondisk %s vs treeinfo: %s" % (opt, csuminfo[0], csum, csuminfo[1])
            continue
    
def main():
    parser = OptionParser()
    parser.usage = """
    verifytree - verify that a local yum repository is consistent
    
    verifytree /path/to/repo"""
    
    parser.add_option("-a","--checkall",action="store_true",default=False,
            help="Check all packages in the repo")
    parser.add_option("-t","--testopia",action="store",type="int",
            help="Report results to the given testopia run number")
    parser.add_option("-r","--treeinfo", action="store_true", default=False,
            help="check the checksums of listed files in a .treeinfo file, if available")
    opts, args = parser.parse_args()
    if not args: 
        print "Must provide a file url to the repo"
        sys.exit(1)
    # FIXME: check that "args" is a valid dir before proceeding 
    # (exists, isdir, contains .treeinfo, etc)

    url = args[0]
    if url[0] == '/':
        url = 'file://' + url

    s = urlparse.urlsplit(url)[0]
    h,d = urlparse.urlsplit(url)[1:3]
    if s != 'file':
        print "Must be a file:// url or you will not like this"
        sys.exit(1)
    repoid = '%s/%s' % (h, d)
    repoid = repoid.replace('/', '_')
    # Bad things happen if we're missing a trailing slash here
    if url[-1] != '/':
        url += '/'

    my = yum.YumBase()
    my.conf.cachedir = getCacheDir()
    my.repos.disableRepo('*')
    newrepo = yum.yumRepo.YumRepository(repoid)
    newrepo.name = repoid
    newrepo.baseurl = [url]
    newrepo.basecachedir = my.conf.cachedir
    newrepo.metadata_expire = 0
    newrepo.enablegroups = 1
    # we want *all* metadata
    newrepo.mdpolicy='group:all'

    # add our new repo
    my.repos.add(newrepo)
    # enable that repo
    my.repos.enableRepo(repoid)
    # setup the repo dirs/etc
    my.doRepoSetup(thisrepo=repoid)

    # Initialize results and reporting
    retval = 0 
    if opts.testopia:
        run_id = testopia_create_run(opts.testopia)
        report = lambda case,result: testopia_report(run_id,case,result)
    else:
        report = lambda case,result: None

    # Check boot images (independent of metadata)
    print "Checking boot images:"
    images_ok = True
    basedir = url.replace('file://', '')
    imagedir = basedir + 'images/'
    for filename in ("boot.iso", "stage2.img"):
        fullpath = imagedir + filename
        try:
            f = open(fullpath)
            data = f.read(1024)
            f.close()
            if len(data) < 1024:
                raise IOError
            print "  verifying %s is a non-empty file" % filename
        except IOError, OSError:
            print "  verifying %s FAILED: missing or unreadable" % filename
            images_ok = False

    if images_ok:
        report('BOOT_IMAGES','PASSED')
    else:
        report('BOOT_IMAGES','FAILED')
        retval = retval | BAD_IMAGES


    # Check the metadata
    print "Checking repodata:"
    try:
        md_types = newrepo.repoXML.fileTypes()
        print "  verifying repomd.xml with yum"
    except yum.Errors.RepoError:
        print "  failed to load repomd.xml."
        report('REPODATA','FAILED')
        report('CORE_PACKAGES','BLOCKED')
        report('COMPS','BLOCKED')
        return retval | BAD_REPOMD

    for md_type in md_types:
        try:
            print "  verifying %s checksum" % md_type
            newrepo.retrieveMD(md_type)
        except Errors.RepoError, e:
            print "  %s metadata missing or does not match checksum" % md_type
            retval = retval | BAD_METADATA
    if retval & BAD_METADATA:
        report('REPODATA','FAILED')
    else:
        report('REPODATA','PASSED')

    print "Checking groups (comps.xml):"
    try:
        print "  verifying comps.xml with yum"
        b = my.comps.compscount
    except Errors.GroupsError, e:
        print '  comps file missing or unparseable'
        report('COMPS','FAILED')
        retval = retval | BAD_COMPS

    if not (retval & BAD_COMPS):
        print "  verifying comps.xml grammar with xmllint"
        comps=newrepo.getGroups()
        r = os.system("xmllint --noout --nowarning --relaxng %s %s" % 
            (SCHEMA,comps))
        if r != 0:
            retval = retval | BAD_COMPS
            report('COMPS','FAILED')
        else:
            report('COMPS','PASSED')

    # if we've got a .treeinfo file and we are told to check it, then do so
    tr_path = basedir + '/.treeinfo'
    if opts.treeinfo and os.path.exists(tr_path):
        print "Checking checksums of files in .treeinfo"
        treeinfo_checksum(tr_path)

    sack = []
    packages_ok = True
    if opts.checkall:
        print "Checking all packages"
        sack = my.pkgSack
    elif not (retval & BAD_COMPS):
        print "Checking mandatory @core packages"
        group = my.comps.return_group('core')
        for pname in group.mandatory_packages:
            # FIXME: this pulls from pkgSack, which (I guess) is populated 
            # based on the arch etc. of the current host.. so you can't check
            # the x86_64 repo from an i386 machine, f'rinstance.
            try:
                sack.extend(my.pkgSack.searchNevra(name=pname))
            except yum.Errors.RepoError:
                print "  something went wrong with the repodata."
                sack = []
                break
    for pkg in sack:
        if checkfileurl(pkg):
            print "  verifying %s checksum" % pkg
        else:
            print "  verifying %s checksum FAILED" % pkg
            packages_ok = False
    if sack:
        if packages_ok is True:
            report('CORE_PACKAGES','PASSED')
        else:
            report('CORE_PACKAGES','FAILED')
            retval = retval | BAD_PACKAGES
    else: 
        # we couldn't test anything
        report('CORE_PACKAGES','BLOCKED')
    # All done!
    if retval == 0:
        print "Tree verified."
    return retval

if __name__ == "__main__":
    r = main()
    sys.exit(r)

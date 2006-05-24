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

# (c) Copyright Seth Vidal 2004

# need hdropen, dir traversing, version comparison, and getopt (eventually)

# this should take a dir, traverse it - build a dict of foo[(name, arch)] = [/path/to/file/that/is/highest, /path/to/equalfile]

import os
import sys
import rpm
import fnmatch
import types
import string
import getopt
from yum import misc
from exceptions import Exception

from optparse import OptionParser


class Error(Exception):
    def __init__(self, args=None):
        Exception.__init__(self)
        self.args = args


def errorprint(stuff):
    print >> sys.stderr, stuff

def rpmOutToStr(arg):
    if type(arg) != types.StringType:
    # and arg is not None:
        arg = str(arg)
        
    return arg

def compareEVR((e1, v1, r1), (e2, v2, r2)):
    # return 1: a is newer than b
    # 0: a and b are the same version
    # -1: b is newer than a
    e1 = rpmOutToStr(e1)
    v1 = rpmOutToStr(v1)
    r1 = rpmOutToStr(r1)
    e2 = rpmOutToStr(e2)
    v2 = rpmOutToStr(v2)
    r2 = rpmOutToStr(r2)
    #print '%s, %s, %s vs %s, %s, %s' % (e1, v1, r1, e2, v2, r2)
    rc = rpm.labelCompare((e1, v1, r1), (e2, v2, r2))
    #print '%s, %s, %s vs %s, %s, %s = %s' % (e1, v1, r1, e2, v2, r2, rc)
    return rc

def returnHdr(ts, package):
    """hand back the rpm header or raise an Error if the pkg is fubar"""
    try:
        fdno = os.open(package, os.O_RDONLY)
    except OSError, e:
        raise Error, "Error opening file %s" % package
    try:
        hdr = ts.hdrFromFdno(fdno)
    except rpm.error, e:
        raise Error, "Error opening package %s" % package
    if type(hdr) != rpm.hdr:
        raise Error, "Error opening package %s" % package
    os.close(fdno)
    return hdr
    
def hdr2pkgTuple(hdr):
    name = hdr['name']
    if hdr[rpm.RPMTAG_SOURCEPACKAGE] == 1:
        arch = 'src'
    else:
        arch = hdr['arch']

    ver = str(hdr['version']) # convert these to strings to be sure
    rel = str(hdr['release'])
    epoch = hdr['epoch']
    if epoch is None:
        epoch = '0'
    else:
        epoch = str(epoch)

    return (name, arch, epoch, ver, rel)
    
    
def getFileList(path, ext, filelist):
    """Return all files in path matching ext, store them in filelist, recurse dirs
       return list object"""
    
    extlen = len(ext)
    try:
        dir_list = os.listdir(path)
    except OSError, e:
        errorprint('Error accessing directory %s, %s' % (path, e))
        raise Error, 'Error accessing directory %s, %s' % (path, e)
        
    for d in dir_list:
        if os.path.isdir(path + '/' + d):
            filelist = getFileList(path + '/' + d, ext, filelist)
        else:
            if string.lower(d[-extlen:]) == '%s' % (ext):
               newpath = os.path.normpath(path + '/' + d)
               filelist.append(newpath)
                    
    return filelist


def trimRpms(rpms, excludeGlobs):
    # print 'Pre-Trim Len: %d' % len(rpms)
    badrpms = []
    for file in rpms:
        for glob in excludeGlobs:
            if fnmatch.fnmatch(file, glob):
                # print 'excluded: %s' % file
                if file not in badrpms:
                    badrpms.append(file)
    for file in badrpms:
        if file in rpms:
            rpms.remove(file)            
    # print 'Post-Trim Len: %d' % len(rpms)
    return rpms


def parseargs(args):
    usage = "repomanage [--old] [--new] path."
    parser = OptionParser(usage=usage)
    
    # new is only used to make sure that the user is not trying to get both 
    # new and old, after this old and not old will be used. 
    # (default = not old = new)
    parser.add_option("-o", "--old", default=False, action="store_true",
      help='print the older packages')
    parser.add_option("-n", "--new", default=False, action="store_true",
      help='print the newest packages')
    parser.add_option("-s", "--space", default=False, action="store_true",
      help='space separated output, not newline')
    parser.add_option("-k", "--keep", default=1, dest='keep', action="store",
      help='newest N packages to keep - defaults to 1')
    parser.add_option("-c", "--nocheck", default=0, action="store_true", 
      help='do not check package paload signatures/digests')
    
    (opts, args)= parser.parse_args()
    
    
    if opts.new and opts.old:
        errorprint('\nPass either --old or --new, not both!\n')
        parser.print_help()
        sys.exit(1)
        
    if len(args) > 1:
        errorprint('Error: Only one directory allowed per run.')
        parser.print_help()
        sys.exit(1)
        
    if len(args) < 1:
        errorprint('Error: Must specify a directory to index.')
        parser.print_help()
        sys.exit(1)
        
    return (opts, args)

def sortByEVR(evr1, evr2):
    """sorts a list of evr tuples"""
    
    rc = compareEVR(evr1, evr2)
    if rc == 0:
        return 0
    if rc < 0:
        return -1
    if rc > 0:
        return 1


def main(args):
    
    (options, args) = parseargs(args)
    mydir = args[0]

    
    rpmList = []
    rpmList = getFileList(mydir, '.rpm', rpmList)
    verfile = {}
    pkgdict = {} # hold all of them - put them in (n,a) = [(e,v,r),(e1,v1,r1)]
    
    keepnum = int(options.keep)*(-1) # the number of items to keep
    
    if len(rpmList) == 0:
        errorprint('No files to process')
        sys.exit(1)
    

    ts = rpm.TransactionSet()
    if options.nocheck:
        ts.setVSFlags(~(rpm._RPMVSF_NOPAYLOAD))
    else:
        ts.setVSFlags(~(rpm.RPMVSF_NOMD5|rpm.RPMVSF_NEEDPAYLOAD))
    for pkg in rpmList:
        try:
            hdr = returnHdr(ts, pkg)
        except Error, e:
            errorprint(e)
            continue
        
        pkgtuple = hdr2pkgTuple(hdr)
        (n,a,e,v,r) = pkgtuple
        del hdr
        
        if not pkgdict.has_key((n,a)):
            pkgdict[(n,a)] = []
        pkgdict[(n,a)].append((e,v,r))
        
        if not verfile.has_key(pkgtuple):
            verfile[pkgtuple] = []
        verfile[pkgtuple].append(pkg)
        
        for natup in pkgdict.keys():
            evrlist = pkgdict[natup]
            if len(evrlist) > 1:
                evrlist = misc.unique(evrlist)
                evrlist.sort(sortByEVR)
                pkgdict[natup] = evrlist
                
    del ts

    # now we have our dicts - we can return whatever by iterating over them
    
    outputpackages = []
    
    #if new
    if not options.old:
        for (n,a) in pkgdict.keys():
            evrlist = pkgdict[(n,a)]
            
            if len(evrlist) < abs(keepnum):
                newevrs = evrlist
            else:
                newevrs = evrlist[keepnum:]
            
            for (e,v,r) in newevrs:
                for pkg in verfile[(n,a,e,v,r)]:
                    outputpackages.append(pkg)
   
    if options.old:
        for (n,a) in pkgdict.keys():
            evrlist = pkgdict[(n,a)]
            
            if len(evrlist) < abs(keepnum):
                continue
 
            oldevrs = evrlist[:keepnum]
            for (e,v,r) in oldevrs:
                for pkg in verfile[(n,a,e,v,r)]:
                    outputpackages.append(pkg)
    
    outputpackages.sort()
    for pkg in outputpackages:
        if options.space:
            print '%s' % pkg,
        else:
            print pkg
        
    
def usage():
    print """
      repomanage [--old] [--new] path
      -o --old - print the older packages
      -n --new - print the newest packages
      -s --space - space separated output, not newline
      -k --keep - newest N packages to keep - defaults to 1
      -c --nocheck - do not check package payload signatures/digests
      -h --help - duh
    By default it will output the full path to the newest packages in the path.
        """
        

if __name__ == "__main__":
    if len(sys.argv) < 1:
        usage()
        sys.exit(1)
    else:
        main(sys.argv[1:])

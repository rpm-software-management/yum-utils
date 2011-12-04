#!/usr/bin/python

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

# (c) Copyright Seth Vidal 2004

# need hdropen, dir traversing, version comparison, and getopt (eventually)

# this should take a dir, traverse it - build a dict of foo[(name, arch)] = [/path/to/file/that/is/highest, /path/to/equalfile]

import os
import sys
import rpm
import fnmatch
import string
import rpmUtils
from yum import misc

from optparse import OptionParser


def errorprint(stuff):
    print >> sys.stderr, stuff
    
    
def getFileList(path, ext, filelist):
    """Return all files in path matching ext, store them in filelist, recurse dirs
       return list object"""
    
    extlen = len(ext)
    try:
        dir_list = os.listdir(path)
    except OSError, e:
        errorprint('Error accessing directory %s, %s' % (path, str(e)))
        return []
        
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
    for fn in rpms:
        for glob in excludeGlobs:
            if fnmatch.fnmatch(fn, glob):
                # print 'excluded: %s' % fn
                if fn not in badrpms:
                    badrpms.append(fn)
    for fn in badrpms:
        if fn in rpms:
            rpms.remove(fn)            
    # print 'Post-Trim Len: %d' % len(rpms)
    return rpms


def parseargs(args):
    usage = """
    repomanage: manage a directory of rpm packages. returns lists of newest 
                or oldest packages in a directory for easy piping to xargs
                or similar programs.
    repomanage [--old] [--new] path.
    """
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
      help='do not check package payload signatures/digests')
    
    (opts, args)= parser.parse_args()
    
    
    if opts.new and opts.old:
        errorprint('\nPass either --old or --new, not both!\n')
        print parser.format_help()
        sys.exit(1)
        
    if len(args) > 1:
        errorprint('Error: Only one directory allowed per run.')
        print parser.format_help()
        sys.exit(1)
        
    if len(args) < 1:
        errorprint('Error: Must specify a directory to index.')
        print parser.format_help()
        sys.exit(1)
        
    return (opts, args)


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
            hdr = rpmUtils.miscutils.hdrFromPackage(ts, pkg)
        except rpmUtils.RpmUtilsError, e:
            msg = "Error opening pkg %s: %s" % (pkg, str(e))
            errorprint(msg)
            continue
        
        pkgtuple = rpmUtils.miscutils.pkgTupleFromHeader(hdr)
        (n,a,e,v,r) = pkgtuple
        del hdr
        
        if (n,a) not in pkgdict:
            pkgdict[(n,a)] = []
        pkgdict[(n,a)].append((e,v,r))
        
        if pkgtuple not in verfile:
            verfile[pkgtuple] = []
        verfile[pkgtuple].append(pkg)
        
    for natup in pkgdict.keys():
        evrlist = pkgdict[natup]
        if len(evrlist) > 1:
            evrlist = misc.unique(evrlist)
            evrlist.sort(rpmUtils.miscutils.compareEVR)
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

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

from exceptions import Exception


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
    ts.setVSFlags(~(rpm.RPMVSF_NOMD5|rpm.RPMVSF_NEEDPAYLOAD))
    try:
        hdr = ts.hdrFromFdno(fdno)
    except rpm.error, e:
        raise Error, "Error opening package %s" % package
    if type(hdr) != rpm.hdr:
        raise Error, "Error opening package %s" % package
    ts.setVSFlags(0)
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
    options = {}
    options['output'] = 'new'
    options['passed'] = []
    options['space'] = 0
    try:
        gopts, argsleft = getopt.getopt(args, 'onhs', ['space', 'new', 'old', 'help'])
    except getopt.error, e:
        errorprint(_('Options Error: %s.') % e)
        usage()
        sys.exit(1)
    
    try: 
        for arg,a in gopts:    
            if arg in ['-h','--help']:
                usage()
                sys.exit(0)
            elif arg in ['-o', '--old']:
                options['output'] = 'old'
                if 'new' in options['passed']:
                    errorprint('\nPass either --old or --new, not both!\n')
                    usage()
                    sys.exit(1)
                else:
                    options['passed'].append('old')
            elif arg in ['-n', '--new']:
                options['output'] = 'new'
                if 'old' in options['passed']:
                    errorprint('\nPass either --old or --new, not both!\n')
                    usage()
                    sys.exit(1)
                else:
                    options['passed'].append('new')
            elif arg in ['-s', '--space']:
                options['space'] = 1
                
            
    except ValueError, e:
        errorprint(_('Options Error: %s') % e)
        usage()
        sys.exit(1)
    
    if len(argsleft) > 1:
        errorprint('Error: Only one directory allowed per run.')
        usage()
        sys.exit(1)
    elif len(argsleft) == 0:
        errorprint('Error: Must specify a directory to index.')
        usage()
        sys.exit(1)
    else:
        directory = argsleft[0]
    
    return options, directory
    
def main(args):
    options, mydir = parseargs(args)
    rpmList = []
    rpmList = getFileList(mydir, '.rpm', rpmList)
    verfile = {}
    naver = {}
    
    if len(rpmList) == 0:
        errorprint('No files to process')
        sys.exit(1)
    
    
    ts = rpm.TransactionSet()
    for pkg in rpmList:
        try:
            hdr = returnHdr(ts, pkg)
        except Error, e:
            errorprint(e)
            continue
        
        pkgtuple = hdr2pkgTuple(hdr)
        (n,a,e,v,r) = pkgtuple
        del hdr
        
        if not verfile.has_key(pkgtuple):
            verfile[pkgtuple] = []
        verfile[pkgtuple].append(pkg)
        
        if not naver.has_key((n,a)):
            naver[(n,a)] = (e,v,r)
            continue
        
        (e2, v2, r2) = naver[(n,a)] # the current champion
        rc = compareEVR((e,v,r), (e2,v2,r2))
        if rc == 0:
            continue
        if rc < 0:
            continue
        if rc > 0:
            naver[(n,a)] = (e,v,r)
    
    del ts
    # now we have our dicts - we can return whatever by iterating over them
    # just print newests
    
    outputpackages = []
    if options['output'] == 'new':
    
        for (n,a) in naver.keys():
            (e,v,r) = naver[(n,a)]
            for pkg in verfile[(n,a,e,v,r)]:
                outputpackages.append(pkg)
   
    if options['output'] == 'old':
        for (n,a,e,v,r) in verfile.keys():
            if (e,v,r) != naver[(n,a,)]:
                for pkg in verfile[(n,a,e,v,r)]:
                    outputpackages.append(pkg)
    
    outputpackages.sort()
    for pkg in outputpackages:
        if options['space']:
            print '%s' % pkg,
        else:
            print pkg
        
    
def usage():
    print """
      repomanage [--old] [--new] path
      -o --old - print the older packages
      -n --new - print the newest packages
      -s --space - space separated output, not newline
      -h --help - duh
    By default it will output the full path to the newest packages in the path.
        """
        

if __name__ == "__main__":
    if len(sys.argv) < 1:
        usage()
        sys.exit(1)
    else:
        main(sys.argv[1:])

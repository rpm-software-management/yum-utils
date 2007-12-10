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

import sys
sys.path.insert(0,'/usr/share/yum-cli')

import yum
from yum.misc import getCacheDir
import yum.misc

from cli import *
from utils import YumUtilBase

from urlparse import urljoin
from urlgrabber.progress import TextMeter


class YumCompleteTransaction(YumUtilBase):
    NAME = 'yum-complete-transactions'
    VERSION = '1.0'
    USAGE = '"usage: yum-complete-transaction [options] package1 [package2] [package..]'
    
    def __init__(self):
        YumUtilBase.__init__(self,
                             YumCompleteTransaction.NAME,
                             YumCompleteTransaction.VERSION,
                             YumCompleteTransaction.USAGE)
        self.logger = logging.getLogger("yum.verbose.cli.yumcompletets")                             
        self.main()

    def clean_up_ts_files(self, timestamp, path):
    
        # clean up the transactions 
        tsdone = '%s/transaction-done.%s' % (path, timestamp)
        tsall = '%s/transaction-all.%s' % (path, timestamp)        
        os.unlink(tsdone)
        os.unlink(tsall)

    def main(self):
        # Add util commandline options to the yum-cli ones
        parser = self.getOptionParser() 
        # Parse the commandline option and setup the basics.
        try:
            opts = self.doUtilConfigSetup()
        except yum.Errors.RepoError, e:
            self.logger.error("Cannot handle specific enablerepo/disablerepo options.")
            sys.exit(50)

        # Check if there is anything to do.
#        if len(self.cmds) < 1: 
#            parser.print_help()
#            sys.exit(0)

        if self.conf.uid != 0:
            self.logger.error("Error: You must be root to finish transactions")
            sys.exit(1)

        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup()
        # Do the real action
        # get the list of transactions remaining
        # list the number of them
        # take the most recent one
        # populate the ts
        # run it
        times = yum.misc.find_unfinished_transactions(self.conf.persistdir)
        if not times:
            print "No unfinished transactions left."      
            sys.exit()
        
        print "There are %d outstanding transactions to complete. Finishing the most recent one" % len(times)    
        
        timestamp = times[-1]
        remaining = yum.misc.find_ts_remaining(timestamp, yumlibpath=self.conf.persistdir)
        print "The remaining transaction had %d elements left to run" % len(remaining)
        for (action, pkgspec) in remaining:
            if action == 'install':
               try:
                   self.install(pattern=pkgspec)
               except yum.Errors.InstallError, e:
                   pass

            if action == 'erase':
               (e, m, u) = self.rpmdb.matchPackageNames([pkgspec])
               for pkg in e:
                   self.remove(po=pkg)
                   
                  

        self.buildTransaction()
        if len(self.tsInfo) < 1:
            print 'Nothing in the unfinished transaction to cleanup.'
            print "Cleaning up completed transaction file"            
            self.clean_up_ts_files(timestamp, self.conf.persistdir)
            sys.exit()
            
        else:            
            if self.doTransaction():
                print "Cleaning up completed transaction file"            
                self.clean_up_ts_files(timestamp, self.conf.persistdir)
                sys.exit()
             


        
        
    
if __name__ == '__main__':
    util = YumCompleteTransaction()
        
       

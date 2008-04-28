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

from cli import *
from utils import YumUtilBase

from urlparse import urljoin
from urlgrabber.progress import TextMeter


try:
   from yum.misc import find_unfinished_transactions, find_ts_remaining
except ImportError:

    import glob
    import os
    import os.path
        
    def find_unfinished_transactions(yumlibpath='/var/lib/yum'):
        """returns a list of the timestamps from the filenames of the unfinished 
           transactions remaining in the yumlibpath specified.
        """
        timestamps = []    
        tsallg = '%s/%s' % (yumlibpath, 'transaction-all*')
        tsdoneg = '%s/%s' % (yumlibpath, 'transaction-done*')
        tsalls = glob.glob(tsallg)
        tsdones = glob.glob(tsdoneg)

        for fn in tsalls:
            trans = os.path.basename(fn)
            timestamp = trans.replace('transaction-all.','')
            timestamps.append(timestamp)

        timestamps.sort()
        return timestamps
        
    def find_ts_remaining(timestamp, yumlibpath='/var/lib/yum'):
        """this function takes the timestamp of the transaction to look at and 
           the path to the yum lib dir (defaults to /var/lib/yum)
           returns a list of tuples(action, pkgspec) for the unfinished transaction
           elements. Returns an empty list if none.

        """
        
        to_complete_items = []
        tsallpath = '%s/%s.%s' % (yumlibpath, 'transaction-all', timestamp)    
        tsdonepath = '%s/%s.%s' % (yumlibpath,'transaction-done', timestamp)
        tsdone_items = []

        if not os.path.exists(tsallpath):
            # something is wrong, here, probably need to raise _something_
            return to_complete_items    

                
        if os.path.exists(tsdonepath):
            tsdone_fo = open(tsdonepath, 'r')
            tsdone_items = tsdone_fo.readlines()
            tsdone_fo.close()     
        
        tsall_fo = open(tsallpath, 'r')
        tsall_items = tsall_fo.readlines()
        tsall_fo.close()
        
        for item in tsdone_items:
            # this probably shouldn't happen but it's worth catching anyway
            if item not in tsall_items:
                continue        
            tsall_items.remove(item)
            
        for item in tsall_items:
            item = item.replace('\n', '')
            if item == '':
                continue
            (action, pkgspec) = item.split()
            to_complete_items.append((action, pkgspec))
        
        return to_complete_items

class YumCompleteTransaction(YumUtilBase):
    NAME = 'yum-complete-transactions'
    VERSION = '1.0'
    USAGE = """
    yum-complete-transaction: completes unfinished yum transactions which occur due to error, failure 
                              or act of $deity
    
    usage: yum-complete-transaction
    """
    
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
        for f in [tsall, tsdone]:
            if os.path.exists(f):
                os.unlink(f)

    def main(self):
        # Add util commandline options to the yum-cli ones
        self.optparser = self.getOptionParser() 
        # Parse the commandline option and setup the basics.
        try:
            opts = self.doUtilConfigSetup()
        except yum.Errors.RepoError, e:
            self.logger.error("Cannot handle specific enablerepo/disablerepo options.")
            sys.exit(50)


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
        times = find_unfinished_transactions(self.conf.persistdir)
        if not times:
            print "No unfinished transactions left."      
            sys.exit()
        
        print "There are %d outstanding transactions to complete. Finishing the most recent one" % len(times)    
        
        timestamp = times[-1]
        remaining = find_ts_remaining(timestamp, yumlibpath=self.conf.persistdir)
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
            if self.doTransaction() == 0:
                print "Cleaning up completed transaction file"            
                self.clean_up_ts_files(timestamp, self.conf.persistdir)
                sys.exit()
            else:
                print "Not removing old transaction files"
                sys.exit()
                             


        
        
    
if __name__ == '__main__':
    util = YumCompleteTransaction()
        
       

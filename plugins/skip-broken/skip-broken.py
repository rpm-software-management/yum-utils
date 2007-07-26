# A plugin for yum, there checks each packages in the transaction 
# for depency errors and remove package with errors from transaction
#
# the plugin will only be active if yum is started with the '--ignore-broken'
# Option.
#
# Ex.
# yum --skip-broken install foo
#
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
# version 0.25 by Tim Lauridsen <tla at rasmil dot dk>

from yum.constants import *
from yum.plugins import TYPE_CORE
import copy
requires_api_version = '2.1'
plugin_type = (TYPE_CORE,)
    
class CheckDependency:
    ''' 
    This class checks if dependencies can be resolved for each package in
    the yum transaction set 
    '''
    def __init__(self,base,log=None):
        self.base = base
        self.logger = log
        
    def resetTs(self):
        '''Clear the current tsInfo Transaction Set'''
        # clear current tsInfo, we want a empty one.
        # FIXME: Dirty Hack, remove it later when then problem dont occour any more.
        # remove depsolver cache.
        if hasattr(self,"dcobj"):
            del self.dcobj            
        del self.base.tsInfo
        self.base.tsInfo = self.base._transactionDataFactory()
        self.base.initActionTs()

    def preDepCheck(self):
        '''
        Check if if each member in self.tsInfo can be depsolved
        without errors.
        '''
        # make a copy of the current self.tsInfo
        saveTs = copy.copy(self.base.tsInfo)
        goodlist = []
        badlist = []
        self.resetTs()
        goodTs = copy.copy(self.base.tsInfo)
        for txmbr in saveTs:
            # check if the member already has been marked as ok
            if goodTs.exists(txmbr.po.pkgtup):
                continue
            self.resetTs()
            po = txmbr.po
            state = txmbr.output_state
            self.logger(2,"**** Checking for dep problems  : %s " % str(txmbr.po))
            self.base.tsInfo.add(txmbr)
            (rescode, restring) = self.base.resolveDeps()
            # Did the resolveDeps want ok ?
            if rescode == 2:
                # transfer all member in this transaction to a good ts.
                for good in self.base.tsInfo:
                    if not goodTs.exists(good.po.pkgtup):
                        self.logger(2,"****   OK : %s" % str(good))
                        goodTs.add(good)
                goodlist.append(txmbr)
            else:
                self.logger(2,"****   Failed ")
                for err in restring:
                    self.logger(2,"****     %s " % err) 
                badlist.append([txmbr,restring])
        # Restore self.tsInfo
        self.resetTs() 
        self.base.tsInfo = goodTs
        return goodlist,badlist
    
    def dumpTsInfo(self):
        ''' show the packages in self.tsInfo '''
        for txmbr in self.base.tsInfo:
            if self.logger:
                self.logger(3," --> %-50s - action : %s" % (txmbr.po,txmbr.ts_state))
            else:
                print " --> %-50s - action : %s" % (txmbr.po,txmbr.ts_state)
            
    

def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Setup the option parser with the '--skip-broken' command line option
    '''
    global check_always
    #  Get 'check_always' option from plugin conf
    check_always = conduit.confBool('main', 'check_always', default=False)    
    
    parser = conduit.getOptParser()
    if parser:
        parser.add_option("", "--skip-broken", dest="skipbroken",
                action="store_true", default=False, 
                help="skip packages with broken dependencies")    
    
def preresolve_hook(conduit):
    '''
    Yum Plugin PreResolve Hook:
    Check and remove packages with dependency problems
    only runs if then '--skip-broken' was set. 
    '''
    opts, commands = conduit.getCmdLine()
    if hasattr(opts,'skipbroken'):
        if opts.skipbroken or check_always:
            # get yum base
            conduit.info(2,'**** Checking packages for dependency problems')
            base = conduit._base
            cd = CheckDependency(base,conduit.info)
            cd.dumpTsInfo()
            (good,bad) = cd.preDepCheck()
            #tsInfo = base.tsInfo
            conduit.info(2,"**** Packages with dependency resolving errors ")
            
            for txmbr,err in bad:
                # Removing bad packages for self.tsInfo
                #tsInfo.remove(txmbr.po.pkgtup)
                conduit.info(2,"**** %s " % txmbr.po)
                for e in err:
                    conduit.info(2,"****   %s " % 2)
            for txmbr in good:
                conduit.info(3,"**** %s completed dependency resolving " % txmbr.po)    
            # Show the current state of y.tsInfo
            conduit.info(2,'**** End Checking packages for dependency problems')
            #cd.dumpTsInfo()
        
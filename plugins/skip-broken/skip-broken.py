# A plugin for yum, there checks each packages in the transaction 
# for depency errors and remove package with errors from transaction
#
# the plugin will only be active if yum is started with the '--ignore-broken'
# Option.
#
# Ex.
# yum --ignore-broken install foo
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
        for txmbr in saveTs:
            self.resetTs()
            po = txmbr.po
            state = txmbr.output_state
            self.base.tsInfo.add(txmbr)
            (rescode, restring) = self.base.resolveDeps()
            # Did the resolveDeps want ok ?
            if rescode == 2:
                goodlist.append(txmbr)
            else:
                badlist.append([txmbr,restring])
        # Restore self.tsInfo
        self.resetTs() 
        self.base.tsInfo = saveTs
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
    Setup the option parser with the '--ignore-broken' command line option
    '''
    parser = conduit.getOptParser()
    if parser:
        parser.add_option("", "--ignore-broken", dest="ignorebroken",
                action="store_true", default=False, 
                help="skip packages with broken dependencies")    
    
def preresolve_hook(conduit):
    '''
    Yum Plugin PreResolve Hook:
    Check and remove packages with dependency problems
    only runs if then '--ignore-broken' was set. 
    '''
    opts, commands = conduit.getCmdLine()
    if hasattr(opts,'ignorebroken'):
        if opts.ignorebroken:
            # get yum base
            conduit.info(2,'Checking packages for dependency problems')
            base = conduit._base
            cd = CheckDependency(base,conduit.info)
            cd.dumpTsInfo()
            (good,bad) = cd.preDepCheck()
            for txmbr,err in bad:
                # Removing bad packages for self.tsInfo
                base.tsInfo.remove(txmbr.po.pkgtup)
                conduit.info(2,"%s failed dependency resolving " % txmbr.po)
                conduit.info(2,"%s " % err[0])
            for txmbr in good:
                conduit.info(3,"%s completed dependency resolving " % txmbr.po)    
            # Show the current state of y.tsInfo
            conduit.info(2,'End Checking packages for dependency problems')
            cd.dumpTsInfo()
        
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

import sys
sys.path.insert(0,'/usr/share/yum-cli')

import logging
from utils import YumUtilBase
from yum.misc import getCacheDir, setup_locale

import yum.Errors


class UtilCheckBase:
    
    def __init__(self):
        pass

    def getNames(self):
        '''
        @return the names of the check used at the command line
        '''
        return []

    def getUsage(self):
        """
        @return: A usage string for the command, including arguments.
        """
        raise NotImplementedError

    def getSummary(self):
        """
        @return: A one line summary of what the command does.
        """
        raise NotImplementedError
    
    def doSetupParser(self, parser):
        '''
        Setup the check's parser options
        @param parser: a OptionParser instance
        '''
        pass

    def doPreSetup(self, base, args, opts):
        '''
        Setup the check before yum is setup
        @param base: yum base class
        @param args: command line args
        @param opts: command line options
        '''
        pass

    def runCheck(self, base,args, opts):
        '''
        Run the check
        @param base: yum base class
        @param args: command line args
        @param opts: command line options
        '''
        raise NotImplementedError
    
    
class TestCheck(UtilCheckBase):
    
    def __init__(self):
        pass

    def getNames(self):
        '''
        @return the names of the check used at the command line
        '''
        return ['test']

    def getUsage(self):
        '''
        @return: A usage string for the command, including arguments.
        '''
        
        return 'test <package> [-all]'

    def getSummary(self):
        '''
        @return: A one line summary of what the command does.
        '''
        return 'Just a test check'
    
    def doSetupParser(self,  parser):
        '''
        Setup the tool and add tool cmd options
        @param parser: OptionParser instance so the tool can add options
        '''
        parser.add_option("--test", default="", dest="test",
          help='test option')

    def doPreSetup(self, base, args, opts):
        '''
        Setup the check before yum is setup
        @param base: yum base class
        @param args: command line args
        @param opts: command line options
        '''
        for repo in base.repos.findRepos('*-source'):
            base.logger.info("Sourcerepo : %s" % repo.id)

    def runCheck(self, base, args, opts):
        '''
        Run the check
        @param args: command line args
        @param opts: command line options
        '''
        if opts.test:
            base.logger.info('OPTION: --test=%s is used' % opts.test)
        for pkg in base.pkgSack:
            if pkg.name.startswith('yum'):
                print pkg


class RepoCheck(YumUtilBase):
    NAME = 'repo-check'
    VERSION = '1.0'
    
    def __init__(self):
        self._checks = {}
        
        # Register checks
        self.registerCheck(TestCheck())
        
        # setup the base
        YumUtilBase.__init__(self,
                             RepoCheck.NAME,
                             RepoCheck.VERSION,
                             self._makeUsage())
        

        self.logger = logging.getLogger("yum.verbose.cli.repo-check")  
        
        
        # get the parser
        self.optparser = self.getOptionParser()
        self.main()
        
    def do_parser_setup(self):    
        if hasattr(self,'getOptionGroup'): # check if the group option API is available
            parser = self.getOptionGroup()
        else:
            parser = self.optparser
            
        # Call the checks parser setup methods 
        for check in self._checks.values():
            check.doSetupParser(parser)
            
        
    def main(self):
        self.do_parser_setup()
        try:
            opts = self.doUtilConfigSetup()
        except yum.Errors.RepoError, e:
            self.logger.error(str(e))
            sys.exit(50)

        # Check if there is anything to do.
        if len(self.cmds) < 1: 
            print self.optparser.format_help()
            sys.exit(0)

        if not self.cmds[0] in self._checks:
            print "\nUnknown Command : %s \n" % self.cmds[0]
            print self.optparser.format_help()
            sys.exit(0)
                
        # Make it work as non root
        if self.conf.uid != 0:
            cachedir = getCacheDir()
            self.logger.debug('Running as non-root, using %s as cachedir' % cachedir)
            if cachedir is None:
                self.logger.error("Error: Could not make cachedir, exiting")
                sys.exit(50)
            self.repos.setCacheDir(cachedir)

            # Turn off cache
            self.conf.cache = 0
            # make sure the repos know about it, too
            self.repos.setCache(0)

        # Run the checks preSetup methods
        if self.cmds[0] in self._checks:
            check = self._checks[self.cmds[0]]
            args = self.cmds[1:]
            check.doPreSetup(self,args,opts)
            
        # Setup yum (Ts, RPM db, Repo & Sack)
        self.doUtilYumSetup()
        
        # Run the check
        if self.cmds[0] in self._checks:
            check = self._checks[self.cmds[0]]
            args = self.cmds[1:]
            self.logger.info("Running the %s check" % self.cmds[0])
            check.runCheck(self,args,opts)
            
    def registerCheck(self, command):
        names = command.getNames()
        for name in names:
            if name in self._checks:
                self.logger.error('Command "%s" already defined' % name)
            self._checks[name] = command

    def _makeUsage(self):
        """
        Format an attractive usage string for yum, listing subcommand
        names and summary usages.
        """
        usage = 'repo-check [options] COMMAND\n\nList of Commands:\n\n'
        commands = yum.misc.unique(self._checks.values())
        commands.sort(cmp=lambda x,y : cmp(x.getNames()[0], y.getNames()[0]))
        for command in commands:
            # XXX Remove this when getSummary is common in plugins
            try:
                summary = command.getSummary()
                usage += "%-14s %s\n" % (command.getNames()[0], summary)
            except (AttributeError, NotImplementedError):
                usage += "%s\n" % command.getNames()[0]

        return usage


if __name__ == '__main__':
    setup_locale()
    util = RepoCheck()
    
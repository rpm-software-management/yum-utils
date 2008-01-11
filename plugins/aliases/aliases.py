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
#
# by James Antill

from yum.plugins import TYPE_INTERACTIVE
import sys
import time
try: # yumex doesn't like import cli, but runs this
    from cli import CliError
except:
    class CliError: # Never used by yumex
        pass

try: # $rand yum using python code don't have i18n
    from i18n import _
except:
    def _(x): return x

requires_api_version = '2.1'
plugin_type = (TYPE_INTERACTIVE,)

class AliasedCommand:
    def __init__(self, cmd):
        self.cmd = cmd
        
    def getNames(self):
        return [self.cmd]

    def getUsage(self):
        return self.getNames()[0]

    # doCheck and doCommand are never called, for aliased commands.


aliases   = None
conffile  = None
recursive = None
def parse_aliases(conffile):
    aliases = {}
    for line in file(conffile):
        args = line.split()
        if len(args) < 2 or args[0][0] == '#':
            continue
        cmd = args.pop(0)
        aliases[cmd] = args
    return aliases

def resolve_aliases(args, log, skip=0):
    need_rep = True
    while need_rep:
        need_rep = False
        num = skip
        for arg in args[skip:]:
            if arg[0] != '-':
                break
            num += 1

        if num >= len(args): # Only options
            break
        
        enum = num + 1
        for cmd in aliases:
            if cmd == args[num]:
                log(3, 'ALIAS DONE(%s): %s' % (cmd, str(aliases[cmd])))
                args[num:enum] = aliases[cmd]
                # Mostly works like the shell, so \ls does no alias lookup on ls
                if args[num][0] == '\\':
                    args[num] = args[num][1:]
                else:
                    need_rep = recursive
                break


class AliasCommand(AliasedCommand):
    def __init__(self):
        AliasedCommand.__init__(self, "alias")

    def doCheck(self, base, basecmd, extcmds):
        if len(extcmds) > 1: # Add a new alias
            try:
                open(conffile, "a").close()
            except:
                base.logger.critical(_("Can't open aliases file: %s") %
                                     conffile)
                raise CliError
                
    def doCommand(self, base, basecmd, extcmds):
        if len(extcmds) > 1: # Add a new alias
            fo = open(conffile, "a")
            fo.write(_("\n# Alias added on %s\n%s\n") % (time.ctime(),
                                                      ' '.join(extcmds)))
            fo.close()
            return 0, [basecmd + ' done']
        
        if len(extcmds) == 1: # Show just a single alias
            cmd = extcmds[0]
            if cmd not in aliases:
                return 1, [_("%s, no match for %s") % (basecmd, cmd)]
                
            args = [cmd]
            resolve_aliases(args, lambda x,y: base.verbose_logger.debug(y))
            print _("Alias %s = %s") % (cmd, " ".join(args))
            return 0, [basecmd + ' done']

        
        for cmd in sorted(aliases.keys()):
            args = aliases[cmd][:]
            resolve_aliases(args, lambda x,y: base.verbose_logger.debug(y))
            print _("Alias %s = %s") % (cmd, " ".join(args))
        
        return 0, [basecmd + ' done']


def config_hook(conduit):
    global aliases
    global conffile
    global recursive
    
    conffile  = conduit.confString('main', 'conffile',
                                  default='/etc/yum/aliases.conf')
    recursive = conduit.confBool('main', 'recursive', default=True)
    register  = conduit.confBool('main', 'register', default=False)

    conduit.registerCommand(AliasCommand())
    aliases = parse_aliases(conffile)
    if register:
        for cmd in aliases:
            conduit.registerCommand(AliasedCommand(cmd))

    # Skip the yum cmd itself
    resolve_aliases(args=sys.argv, skip=1, log=conduit.info)


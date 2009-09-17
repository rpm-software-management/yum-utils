#! /usr/bin/python -tt
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
#
# Copyright Red Hat Inc. 2008
#
# Author: James Antill <james.antill@redhat.com>
#
# Examples:
#
#  yum verify
#  yum verify yum*
#  yum verify all
#  yum verify extras


from yum.plugins import TYPE_INTERACTIVE
import logging # for commands
from yum import logginglevels

import time
import stat

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)

def nevr(pkg):
    """ Identify a pkg without arch. """
    return "%s-%s:%s-%s" % (pkg.name, pkg.epoch, pkg.version, pkg.release)

def fmt_rwx(mode, r, w, x):
    ret = []
    
    if w & mode:
        ret.append("w")
    else:
        ret.append("-")
    if r & mode:
        ret.append("r")
    else:
        ret.append("-")
    if x & mode:
        ret.append("x")
    else:
        ret.append("-")

    return "".join(ret)    

def format_mode(mode):
    ret = []
    tmp = []
    if stat.S_ISUID & mode:
        tmp.append("set user (setuid)")
    if stat.S_ISGID & mode:
        tmp.append("set group (setgid)")
    if stat.S_ISVTX & mode:
        tmp.append("sticky")
    if tmp:
        ret.append("/".join(tmp))
    
    ret.append("user:"  + fmt_rwx(mode, stat.S_IRUSR,stat.S_IWUSR,stat.S_IXUSR))
    ret.append("group:" + fmt_rwx(mode, stat.S_IRGRP,stat.S_IWGRP,stat.S_IXGRP))
    ret.append("other:" + fmt_rwx(mode, stat.S_IROTH,stat.S_IWOTH,stat.S_IXOTH))
    return ", ".join(ret)

import datetime
def format_time_diff(x, y):
    frm = datetime.datetime.fromtimestamp
    if x > y:
        return str(frm(x) - frm(y)) + " later"
    else:
        return str(frm(y) - frm(x)) + " earlier"

def problem_contains(problems, types):
    for problem in problems:
        if problem.type in types:
            return problem
    return None

def pkg_multilib_file(data, pkg, pkgs, fname):

    problems = data[pkg][fname]
    ml_csum = problem_contains(problems, ['checksum'])
    ml_size = problem_contains(problems, ['size'])
    ml_time = problem_contains(problems, ['mtime'])
    if not (ml_csum or ml_size or ml_time):
        return False

    for opkg in pkgs:
        if opkg == pkg:
            continue

        if opkg not in data:
            data[opkg] = opkg.verify()
        if fname not in data[opkg]:
            return True

        if problem_contains(problems, ['state', 'missingok', 'ghost']):
            continue
        
        problems = data[opkg][fname]
        srch = []
        if ml_csum:
            srch.append('checksum')
        if ml_size:
            srch.append('size')
        if ml_time:
            srch.append('mtime')
        if problem_contains(problems, srch):
            continue

        return True
        
    return False

# We make decisions based on these
_verify_multilib = ['mtime', 'size', 'checksum']
_verify_missingok= ['missingok', 'ghost']
_verify_none     = ['state'] + _verify_missingok
_verify_missing  = ['missing', 'permissions-missing','genchecksum']+_verify_none

# These are user configurable, for output
_verify_low      = ['mtime', 'genchecksum', 'permissions-missing'] +_verify_none
_verify_onohi    = ['mtime', 'checksum']
_verify_nnohi    = ['mtime', 'checksum']
_verify_configs  = False

class VerifyCommand:

    def __init__(self, names, conf, multilib=True, verify_configs_override=None,
                 all=False):
        self.names = names
        self.conf  = conf
        self.all = all
        self.multilib = multilib
        self.verify_configs_override = verify_configs_override

    def getNames(self):
        return self.names

    def getUsage(self):
        return "[PACKAGE|all|extras]"

    def getSummary(self):
        return """\
Verify packages and display data on bad verifications"""

    def doCheck(self, base, basecmd, extcmds):
        pass

    def show_pkgs(self, msg, pkgs):
        pass

    @staticmethod
    def _filter_results(oresults, verify_none=None):
        if verify_none is None:
            verify_none = _verify_none
        results = {}
        for fn in oresults:
            probs = []
            for problem in oresults[fn]:
                if problem.type not in verify_none:
                    probs.append(problem)
            if probs:
                results[fn] = probs
        return results

    @staticmethod
    def _filter_empty(oresults):
        results = {}
        for fname in oresults:
            if oresults[fname]:
                results[fname] = oresults[fname]
        return results

    def _filter_multilib(self, data, pkg, results):
        for fname in results:
            problems = results[fname]
            mpkgs = self._multilib[nevr(pkg)]
            if not pkg_multilib_file(data, pkg, mpkgs, fname):
                continue

            tmp = []
            for problem in problems:
                if problem.type in _verify_multilib:
                    continue
                tmp.append(problem)
            results[fname] = tmp
        return self._filter_empty(results)

    def filter_data(self, msg, pkgs):
        data = {}
        for pkg in sorted(pkgs):
            oresults = pkg.verify(patterns=self._filename_globs, all=self.all)

            if not _verify_configs and not self.verify_configs_override:
                for fn in oresults.keys():
                    if 'configuration' in oresults[fn][0].file_types:
                        del oresults[fn]
                
            if self.multilib:
                data[pkg] = oresults
            else:
                if self.all:
                    results = self._filter_results(oresults, _verify_missingok)
                else:
                    results = self._filter_results(oresults)
                if results:
                    yield (pkg, results)
            
        if not self.multilib:
            return

        ndata = {}
        for pkg in data:
            results = self._filter_results(data[pkg])
            if nevr(pkg) in self._multilib:
                ndata[pkg] = self._filter_multilib(data, pkg, results)
            else:
                ndata[pkg] = results
        
        for pkg in sorted(pkgs):
            if pkg in ndata and ndata[pkg]:
                yield (pkg, ndata[pkg])

    def _mode_except(self, base, line, problem=None, exceptions=None):
        if exceptions is None:
            exceptions = _verify_low
        if problem is not None and problem.type in exceptions:
            return ("", "")
        
        hib = ""
        hie = ""

        name = 'fg_' + line
        if name in self.conf and self.conf[name] in base.term.FG_COLOR:
            hib += base.term.FG_COLOR[self.conf[name]]
        name = 'bg_' + line
        if name in self.conf and self.conf[name] in base.term.BG_COLOR:
            hib += base.term.BG_COLOR[self.conf[name]]
        name = 'hi_' + line
        if name in self.conf and self.conf[name] in base.term.MODE:
            hib += base.term.MODE[self.conf[name]]
            
        hie = base.term.MODE['normal']
        return (hib, hie)

    def show_problem(self, base, msg, problem, done):
        if done:
            msg("%s%s%s" % (' ' * 35, '-' * 8, ' ' * 35))
        (hib, hie) = self._mode_except(base, 'prob', problem)
        msg("        Problem:  " + hib + problem.message + hie)
        if problem.type not in _verify_missing:
            cv = problem.disk_value
            ov = problem.database_value
            if problem.type == 'mtime':
                cv = time.ctime(cv) + " (%s)" % format_time_diff(cv, ov)
                ov = time.ctime(ov)
            if problem.type == 'mode':
                cv = format_mode(cv)
                ov = format_mode(ov)
            if problem.type == 'size':
                cv = "%*s" % (5, base.format_number(cv))
                ov = "%*s" % (5, base.format_number(ov))
                if cv == ov: # ignore human units, so we can see the diff.
                    cv = "%*s B" % (12, str(problem.disk_value))
                    ov = "%*s B" % (12, str(problem.database_value))

            (hib, hie) = self._mode_except(base, 'new', problem, _verify_nnohi)
            msg("        Current:  " + hib + cv + hie)
            (hib, hie) = self._mode_except(base, 'old', problem, _verify_onohi)
            msg("        Original: " + hib + ov + hie)
        
    def show_data(self, base, msg, pkgs, name):
        done = False
        mcb = lambda x: base.matchcallback(x, [])
        for (pkg, results) in self.filter_data(msg, pkgs):
            if not done:
                msg("%s %s %s" % ('=' * 20, name, '=' * 20))
            else:
                msg('')
            done = True
            
            mcb(pkg)
            for fname in sorted(results):
                hiprobs = len(filter(lambda x: x.type not in _verify_low,
                                     results[fname]))
                if hiprobs:
                    (hib, hie) = self._mode_except(base, 'file')
                else:
                    (hib, hie) = ("", "")
                msg("    File: " + hib + fname + hie)
                if hiprobs:
                    (hib, hie) = self._mode_except(base, 'tags')
                else:
                    (hib, hie) = ("", "")
                done_prob = False
                for problem in sorted(results[fname]):
                    if not done_prob and problem.file_types:
                        tags = ", ".join(problem.file_types)
                        msg("    Tags: " + hib + tags + hie)
                    self.show_problem(base, msg, problem, done_prob)
                    done_prob = True

    def doCommand(self, base, basecmd, extcmds):
        logger = logging.getLogger("yum.verbose.main")
        def msg(x):
            logger.log(logginglevels.INFO_2, x)
        def msg_warn(x):
            logger.warn(x)

        opts = base.plugins.cmdline[0]
        if opts.verify_configuration_files is not None:
            val = opts.verify_configuration_files
            if False: pass
            elif val.lower() in ["0", "no", "false", "off"]:
                _verify_configs = False
            elif val.lower() in ["1", "yes", "true", "on"]:
                _verify_configs = True
            else:
                msg_warn("Ignoring bad value \"%s\" for the option %s" %
                         (val, "--verify-configuration-files"))
        self._filename_globs = None
        if opts.verify_filenames:
            self._filename_globs = opts.verify_filenames
            
        subgroup = ["installed"]
        if len(extcmds):
            if extcmds[0] == "all":
                extcmds = extcmds[1:]
            elif extcmds[0] == "extras":
                subgroup = ["extras"]
                extcmds = extcmds[1:]

        if self.multilib:
            pkgs = base.returnPkgLists(["installed"]).installed
            self._multilib = {}
            for pkg in pkgs:
                self._multilib.setdefault(nevr(pkg), []).append(pkg)
            for pkg in pkgs:
                if len(self._multilib[nevr(pkg)]) == 1:
                    del self._multilib[nevr(pkg)]
            # self._multilib is now a dict of all pkgs that have more than one
            # nevr() match
            
        ypl = base.returnPkgLists(subgroup + extcmds)
        self.show_data(base, msg, ypl.installed, 'Installed Packages')
        self.show_data(base, msg, ypl.extras,    'Extra Packages')

        return 0, [basecmd + ' done']

    def needTs(self, base, basecmd, extcmds):
        if not len(extcmds) or extcmds[0] != 'extras':
            return False
        
        return True


def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    Add the 'verify' and 'verify-no-multilib' commands.
    '''
    global _verify_configs
    global _verify_low
    global _verify_onohi
    global _verify_nnohi

    _verify_configs = conduit.confBool('main', 'configuration-files',
                                       default=False)
    
    low = conduit.confString('highlight', 'low-priority', default=None)
    if low:
        _verify_low   = filter(len, low.replace(',', ' ').split())
    fold = conduit.confString('highlight', 'filter-old', default=None)
    if fold:
        _verify_onohi = filter(len, fold.replace(',', ' ').split())
    fnew = conduit.confString('highlight', 'filter-new', default=None)
    if fnew:
        _verify_nnohi = filter(len, fnew.replace(',', ' ').split())

    conf = {}

    conf['hi_prob'] = conduit.confString('highlight', 'problem', default='bold')
    conf['fg_prob'] = conduit.confString('highlight', 'problem-fg',default=None)
    conf['bg_prob'] = conduit.confString('highlight', 'problem-bg',default=None)
    
    conf['hi_new'] = conduit.confString('highlight', 'new', default='reverse')
    conf['fg_new'] = conduit.confString('highlight', 'new-fg', default=None)
    conf['bg_new'] = conduit.confString('highlight', 'new-bg', default=None)
    
    conf['hi_old'] = conduit.confString('highlight', 'old',    default=None)
    conf['fg_old'] = conduit.confString('highlight', 'old-fg', default='red')
    conf['bg_old'] = conduit.confString('highlight', 'old-bg', default=None)
    
    conf['hi_file'] = conduit.confString('highlight', 'file',
                                         default='underline')
    conf['fg_file'] = conduit.confString('highlight', 'file-fg',
                                         default='green')
    conf['bg_file'] = conduit.confString('highlight', 'file-bg', default=None)
    
    conf['hi_tags'] = conduit.confString('highlight', 'tags',    default='bold')
    conf['fg_tags'] = conduit.confString('highlight', 'tags-fg',
                                         default='yellow')
    conf['bg_tags'] = conduit.confString('highlight', 'tags-bg',
                                         default='black')

    reg = conduit.registerCommand
    reg(VerifyCommand(['verify-all'], conf, multilib=False,
                      verify_configs_override=True, all=True))
    reg(VerifyCommand(['verify-rpm'], conf, multilib=False,
                      verify_configs_override=True))
    reg(VerifyCommand(['verify-multilib','verify'], conf))

    parser = conduit.getOptParser()
    if not parser:
        return

    def make_nopt(attrs):
        attrs = attrs.replace("-", "_")
        def func(opt, key, val, parser):
            vals = str(val).replace(",", " ").split()
            vals = filter(len, vals)
            getattr(parser.values, 'verify_' + attrs).extend(vals)
        return func

    if hasattr(parser, 'plugin_option_group'):
        parser = parser.plugin_option_group
    parser.add_option('--verify-filenames', action="callback",
                      callback=make_nopt('filenames'), default=[],type="string",
                      help='Only verify files matching this')

    parser.add_option('--verify-configuration-files', action="store",
                      type="string",
                      help='Verify files tagged as configuration files')

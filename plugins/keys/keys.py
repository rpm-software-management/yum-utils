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
import rpmUtils.transaction

import time
import fnmatch
import yum.pgpmsg

requires_api_version = '2.1'
plugin_type = (TYPE_INTERACTIVE,)

def match_one_of(patterns, key):
    for pat in patterns:
        if pat == key.keyid:
            return True
        if pat == "%s-%x" % (key.keyid, key.createts):
            return True
        if fnmatch.fnmatch(key.sum_auth, pat):
            return True
    return False

class Key:

    def __init__(self, keyid, createts, sum_type, sum_auth, data):
        self.keyid    = keyid
        self.createts = createts
        self.sum_type = sum_type
        self.sum_auth = sum_auth
        self.data     = data

    def __cmp__(self, other):
        if other is None:
            return 1

        ret = cmp(self.sum_type, self.sum_type)
        if ret: return ret
        ret = cmp(self.sum_auth, self.sum_auth)
        if ret: return ret
        ret = cmp(self.keyid, self.keyid)
        if ret: return ret
        # Never gets here on diff. keys?
        ret = cmp(self.createts, self.createts)
        return ret

class KeysListCommand:

    def getNames(self):
        return ["keys", "keys-list"]

    def getUsage(self):
        return "[key-wildcard]"

    def getSummary(self):
        return "Lists keys for signing data"

    def doCheck(self, base, basecmd, extcmds):
        pass

    def show_hdr(self):
        print "%-4.4s %-66.66s %s" % ("Type", "Key owner", "Key ID")

    def show_key(self, key):
        print "%-4.4s %-66.66s %s" % (key.sum_type, key.sum_auth, key.keyid)

    def doCommand(self, base, basecmd, extcmds):
        keys = []
        ts = rpmUtils.transaction.TransactionWrapper(base.conf.installroot)
        for hdr in ts.dbMatch('name', 'gpg-pubkey'):
            keyid    = hdr['version']
            createts = int(hdr['release'], 16)

            sum_auth = hdr['summary']
            sum_auth = sum_auth.strip()
            if not sum_auth.startswith('gpg(') or not sum_auth.endswith(')'):
                sum_type = "<?>"
            else:
                sum_auth = sum_auth[4:-1]
                sum_type = "GPG"

            data = hdr['description']

            keys.append(Key(keyid, createts, sum_type, sum_auth, data))

        done = False
        for key in sorted(keys):
            if not len(extcmds) or match_one_of(extcmds, key):
                if not done:
                    self.show_hdr()
                done = True
                self.show_key(key)
        
        return 0, [basecmd + ' done']

    def needTs(self, base, basecmd, extcmds):
        return False

class KeysInfoCommand(KeysListCommand):

    def getNames(self):
        return ["keys-info"]

    def getSummary(self):
        return "Full information keys for signing data"

    def show_hdr(self):
        pass

    def show_key(self, key):
        if key.sum_type == '<?>':
            print """\
Type      : %s
Key owner : %s
Rpm Key ID: %s
Created   : %s
""" % (key.sum_type, key.sum_auth, key.keyid, time.ctime(key.createts))
        else:
            gpg_cert = yum.pgpmsg.decode_msg(key.data)
            print """\
Type       : %s
Key owner  : %s
Rpm Key ID : %s
Created    : %s
Version    : PGP Public Key Certificate v%d
Primary ID : %s
Algorithm  : %s
Fingerprint: %s
Key ID     : %s
""" % (key.sum_type, key.sum_auth, key.keyid, time.ctime(key.createts),
       gpg_cert.version, gpg_cert.user_id,
       yum.pgpmsg.algo_pk_to_str[gpg_cert.public_key.pk_algo],
       yum.pgpmsg.str_to_hex(gpg_cert.public_key.fingerprint()),
       yum.pgpmsg.str_to_hex(gpg_cert.public_key.key_id()))


class KeysDataCommand(KeysListCommand):

    def getNames(self):
        return ["keys-data"]

    def getSummary(self):
        return "Show public key block information for signing data"

    def show_hdr(self):
        pass

    def show_key(self, key):
        print """\
Type     : %s
Key owner: %s
Key ID   : %s
Created  : %s
Raw Data :
  %s
""" % (key.sum_type, key.sum_auth, key.keyid, time.ctime(key.createts),
       key.data.replace('\n', '\n  '))


def config_hook(conduit):
    conduit.registerCommand(KeysListCommand())
    conduit.registerCommand(KeysInfoCommand())
    conduit.registerCommand(KeysDataCommand())

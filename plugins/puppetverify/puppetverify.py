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

# Copyright 2011 Red Hat, Inc
# written by Seth Vidal <skvidal@fedoraproject.org>

# this plugin will modify the verify checks with the checksums
# from the files in puppet - so you don't get false positives versus 
# what puppet thinks the file should be.


from yum.plugins import TYPE_CORE
from yum.constants import *
import yaml
import os


def generic_string_constructor(loader, node):          
   return loader.construct_scalar(node)       

yaml.add_constructor(u'!ruby/sym', generic_string_constructor)



requires_api_version = '2.4'
plugin_type = (TYPE_CORE,)
yaml_data = {}


def get_checksum(thisfn):
    global yaml_data
    if os.path.exists(puppet_state_file):
        if not yaml_data:
            yaml_data = yaml.load(open(puppet_state_file, 'r').read())
            
        p_fn = "File[%s]" % thisfn
        if p_fn not in yaml_data:
            return

        v = yaml_data[p_fn]
        if 'checksums' in v:
            if 'md5' in v['checksums']: # are puppet checksums in anything else?
                csum = v['checksums']['md5'].replace('{md5}', '')
            return ('md5', csum)


def verify_package_hook(conduit):
    for i in conduit.verify_package:
        results = get_checksum(i.filename)
        if not results: continue
        i.digest = results # tuple(csumtype, csum)
        # you can set other values like file mode, size, date, etc here
        
   
def config_hook(conduit):
    '''
    Yum Plugin Config Hook: 
    '''
    global puppet_state_file
    puppet_state_file = conduit.confString('main', 'puppet_state_file', default='/var/lib/puppet/state/state.yaml')


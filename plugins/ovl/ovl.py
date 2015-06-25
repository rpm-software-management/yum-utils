# Copyright (C) 2015  Red Hat, Inc.
#
# Authors: Pavel Odvody <podvody@redhat.com>
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.

from yum.plugins import TYPE_CORE
from os import utime, walk, path

requires_api_version = '2.3'
plugin_type = (TYPE_CORE,)
base_dir = 'var/lib/rpm/'
mtab = '/etc/mtab'

def should_touch():
    """ 
    Touch the files only once we've verified that
    we're on overlay mount
    """
    with open(mtab, 'r') as f:
        line = f.readline()
        return line and line.startswith('overlay /')
    return False

def init_hook(conduit):
    if not should_touch():
        return
    ir = conduit.getConf().installroot
    try:
        for root, _, files in walk(path.join(ir, base_dir)):
            for f in files:
                p = path.join(root, f)
                with open(p, 'a'):
                    utime(p, None)
    except Exception as e:
        conduit.error(1, "Error while doing RPMdb copy-up:\n%s" % e)

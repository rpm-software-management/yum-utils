# -*- coding: utf-8 -*-
#
# Copyright (c) 2009 Ville Skyttä <ville.skytta at iki.fi>
#
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

"""
B{show-leaves} is a Yum plugin which shows newly installed leaf packages and
packages that became leaves after a transaction.
"""

from yum.plugins import TYPE_INTERACTIVE

requires_api_version = '2.4'
plugin_type = (TYPE_INTERACTIVE,)

_old_leaves = None
_new_leaves = None

def _get_installed_leaves(conduit):
    ret = set()
    for po in conduit.getRpmDB().returnLeafNodes():
        ret.add((po.name, po.arch))
    return ret

def pretrans_hook(conduit):
    global _old_leaves
    _old_leaves = _get_installed_leaves(conduit)

def posttrans_hook(conduit):
    global _new_leaves
    _new_leaves = _get_installed_leaves(conduit)

def close_hook(conduit):
    global _old_leaves, _new_leaves
    if _old_leaves is None or _new_leaves is None:
        return
    newleaves = _new_leaves - _old_leaves
    if newleaves:
        conduit.info(2, "New leaves:")
        for leaf in sorted(newleaves):
            conduit.info(2, "  %s.%s" % leaf)
    

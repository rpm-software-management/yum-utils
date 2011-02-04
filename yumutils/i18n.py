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

"""
The yumutils.i18n pythom module for i18n code used by utils and plugins
"""

# flag to disable i18n, set it to false to enable dummy wrappers.
_use_i18n = True

    
def dummy_wrapper(str):
    '''
    Dummy Translation wrapper, just returning the same string.
    '''
    return str

def dummyP_wrapper(str1, str2, n):
    '''
    Dummy Plural Translation wrapper, just returning the singular or plural
    string.
    '''
    if n == 1:
        return str1
    else:
        return str2

if _use_i18n:
    try:
        from kitchen.i18n import easy_gettext_setup
        # setup the translation wrappers
        _, P_  = easy_gettext_setup('yum-utils') 
    except:
        _ = dummy_wrapper
        P_ = dummyP_wrapper
else:
    _ = dummy_wrapper
    P_ = dummyP_wrapper
    

# A plugin for yum which notifies yum-updatesd to refresh its data
#
# Written by James Bowes <jbowes@redhat.com>
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
# version 0.0.5

import dbus
from yum.plugins import TYPE_CORE

requires_api_version = '2.5'
plugin_type = TYPE_CORE

def posttrans_hook(conduit):
    """
    Tell yum-updatesd to refresh its state. Run only after an rpm transaction.
    """
    try:
        bus = dbus.SystemBus()
    except dbus.DBusException, e:
        conduit.info(2, "Unable to connect to dbus")
        conduit.info(6, "%s" %(e,))
        return
    try:
        o = bus.get_object('org.freedesktop.DBus', '/')
        if not o.NameHasOwner("edu.duke.linux.yum"):
            conduit.info(2, "yum-updatesd not on the bus")
            return
    except dbus.DBusException, e:
        conduit.info(2, "Unable to look at what's on dbus")
        conduit.info(6, "%s" %(e,))
        return
    try:
        updatesd_proxy = bus.get_object('edu.duke.linux.yum', '/Updatesd')
        updatesd_iface = dbus.Interface(updatesd_proxy, 'edu.duke.linux.yum')
        updatesd_iface.CheckNow()
    except dbus.DBusException, e:
        conduit.info(2, "Unable to send message to yum-updatesd")
        conduit.info(6, "%s" %(e,))

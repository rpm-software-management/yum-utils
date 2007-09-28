# A plugin for yum which notifies yum-updatesd to refresh it's data
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
# version 0.0.3

import dbus
from yum.plugins import TYPE_CORE

requires_api_version = '2.5'
plugin_type = TYPE_CORE

repos_setup = False

def postreposetup_hook(conduit):
    global repos_setup
    repos_setup = True

def posttrans_hook(conduit):
    if not repos_setup:
        return

    try:
        bus = dbus.SystemBus()
    except dbus.DBusException:
        conduit.info(2, "Unable to connect to dbus")
        return
    try:
        updatesd_proxy = bus.get_object('edu.duke.linux.yum', '/Updatesd')
        updatesd_iface = dbus.Interface(updatesd_proxy, 'edu.duke.linux.yum')
        updatesd_iface.CheckNow()
    except dbus.DBusException:
        conduit.info(2, "Unable to send message to yum-updatesd")

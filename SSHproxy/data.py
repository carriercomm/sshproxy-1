#!/usr/bin/python
# -*- coding: ISO-8859-15 -*-
#
# Copyright (C) 2005 David Guerizec <david@guerizec.net>
#
# Last modified: 2006 jan 19, 17:02:36 by david
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307  USA


# Imports from Python
from pwdb import MySQLPwDB
from util import SSHProxyError

# XXX: this class should be a singleton
class UserData(object):
    def __init__(self):
        self.pwdb = MySQLPwDB()
        self.sitelist = []
        self.sitedict = {}

    def valid_auth(self, username, password=None, key=None):
        if not self.pwdb.is_allowed(username=username,
                                    password=password,
                                    key=key):
            if key is not None:
                self.unauth_key = key
            return False
        else:
            if key is None and hasattr(self, 'unauth_key'):
                self.pwdb.set_user_key(self.unauth_key)
            self.username = username
            return True

    def is_admin(self):
        return self.is_authenticated() and self.pwdb.is_admin()
            
    def is_authenticated(self):
        return hasattr(self, 'username')
        
    def set_channel(self, channel):
        self.channel = channel

    def add_site(self, sitename):
        sitedata = SiteData(self, sitename)
        self.sitedict[sitedata.sitename] = sitedata
        self.sitelist.append(sitedata.sitename)
        # return real sitename (user@sid)
        return sitedata.sitename

    def get_site(self, sitename=None, index=0):
        if not sitename:
            if len(self.sitelist):
                return self.sitedict[self.sitelist[index]]
            else:
                return None
        elif sitename in self.sitelist:
            return self.sitedict[sitename]
        else:
            return None

    def list_sites(self):
        return self.sitelist

class SiteData(object):
    def __init__(self, userdata, sitename):
        self.userdata = userdata

        try:
            user, site = userdata.pwdb.get_site(sitename)
        except AttributeError, msg:
            raise SSHProxyError(msg)

        if not site:
            raise SSHProxyError("Site %s does not exist in the database" % sitename)
        self.sid = site.sid
        self.username = user
        self.sitename = '%s@%s' % (user, site.sid)

        self.hostname = site.ip_address
        self.port = site.port
        # TODO: check the hostkey (add a column in mysql.sshproxy.site)
        self.hostkey = None

        self.sitedata = site
        self.password = site.users[user].password

        self.type = 'shell'
        self.cmdline = None
        self.path = None
    
    def set_type(self, type):
        # 'shell' or 'sftp'
        self.type = type
        
    def set_cmdline(self, cmdline):
        self.cmdline = cmdline

    def set_sftp_path(self, path):
        self.path = path

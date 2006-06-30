#!/usr/bin/env python
# -*- coding: ISO-8859-15 -*-
#
# Copyright (C) 2005-2006 David Guerizec <david@guerizec.net>
#
# Last modified: 2006 Jun 30, 23:38:25 by david
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA


from Crypto.Cipher import Blowfish
import base64

from config import Config, ConfigSection, get_config

_engine_registry = {}


def register_engine(cls):
    _engine_registry[cls.cipher_id] = cls

def get_engine(cipher_type):
    engine = _engine_registry.get(cipher_type, None)
    if engine is None:
        if cipher_type != 'plain':
            raise ValueError('Unknown cipher_type %s' % cipher_type)
        engine = PlainCipher
    return engine

def cipher(text, **kw):
    engine = _default_engine[0]
    if kw.has_key('type'):
        engine = get_engine(kw['type'])
    return '%s%s' % (engine.prefix(), engine.encrypt(text, **kw))

def decipher(text, **kw):
    # guess the encryption method
    tokens = text.split('$', 2)

    # default decoder is Plain
    engine = PlainCipher
    if len(tokens) == 3:
        try:
            engine = get_engine(tokens[1])
            text = tokens[2]
        except ValueError:
            # maybe the text contains the magic prefix...
            # let's try to decode it as plain text
            pass

    return engine.decrypt(text, **kw)

class BaseCipher(object):
    # cipher_id = ''

    @classmethod
    def set_default(cls):
        _default_engine[0] = cls

    @classmethod
    def prefix(cls):
        return '$%s$' % cls.cipher_id

    @classmethod
    def encrypt(cls, text, **kw):
        raise NotImplementedError

    @classmethod
    def decrypt(cls, text, **kw):
        raise NotImplementedError

class PlainCipher(BaseCipher):
    cipher_id = "plain"

    @classmethod
    def prefix(cls):
        return ''

    @classmethod
    def encrypt(cls, text, **kw):
        return text

    @classmethod
    def decrypt(cls, text, **kw):
        return text

class Base64Cipher(BaseCipher):
    cipher_id = "base64"

    @classmethod
    def encrypt(cls, text, **kw):
        return base64.b64encode(text)

    @classmethod
    def decrypt(cls, text, **kw):
        return base64.b64decode(text)

register_engine(Base64Cipher)

class BlowfishCipher(BaseCipher):
    cipher_id = "blowfish"

    @classmethod
    def set_default(cls):
        cls.engine = cls.get_engine(get_config('blowfish')['secret'])
        _default_engine[0] = cls

    @classmethod
    def get_engine(cls, secret=None):
        if secret is None:
            secret = getattr(cls, 'secret', get_config('blowfish')['secret'])
        return Blowfish.new(secret, Blowfish.MODE_ECB)

    @classmethod
    def encrypt(cls, text, **kw):
        engine = kw.get('engine', getattr(cls, 'engine', None))
        if not engine:
            engine = cls.get_engine(kw.get('secret', None))
        ftext = '%s:%s%s' % (len(text), text, '*'*8)
        ftext = ftext[:len(ftext) - (len(ftext)%8) ]
        return base64.b64encode(engine.encrypt(ftext))

    @classmethod
    def decrypt(cls, text, **kw):
        engine = kw.get('engine', getattr(cls, 'engine', None))
        if not engine:
            engine = cls.get_engine(kw.get('secret', None))
        crypted = base64.b64decode(text)
        # an exception here means we've lost the key...
        # how to handle that situation ?
        size, ftext = engine.decrypt(crypted).split(':', 1)
        return ftext[:int(size)]

register_engine(BlowfishCipher)

_default_engine = [ PlainCipher ]

class BlowfishConfigSection(ConfigSection):
    section_defaults = {
        'secret': ('Enoch Root has an old cigar box on his lap.'
        ' Golden light is shining out of the crack around its lid.'),
        }

    def __setitem__(self, option, value):
        ConfigSection.__setitem__(self, option, value)
        if option == 'secret':
            reload()

Config.register_handler('blowfish', BlowfishConfigSection)

def _init_cipher():
    cipher_type = get_config('sshproxy')['cipher_type']
    get_engine(cipher_type).set_default()

_init_cipher()

reload = _init_cipher


#######################################################################
### Recipher database
#######################################################################


def recipher(cipher_type, password_fd, dry_run=False):
    import sys, getpass
    from sshproxy.backend import get_backend

    conf = get_config()

    newsecret = ''
    if cipher_type == 'blowfish':
        if conf['sshproxy']['cipher_type'] == 'blowfish':
            print("Recipher from blowfish to blowfish does not work "
                  "at the moment.\nPlease recipher to base64 first, "
                  "then recipher to blowfish.")
            print "Sorry for the inconvenience."
            sys.exit(0)
        try:
            if password_fd == True:
                newsecret = conf['blowfish']['secret']
            elif not password_fd:
                sec1 = 1
                sec2 = 2
                while not sec1 or sec1 != sec2:
                    sec1 = getpass.getpass("Enter secret (1/2) ")
                    sec2 = getpass.getpass("Enter secret (2/2) ")
                newsecret = sec1
            else:
                try:
                    newsecret = password_fd.readlines()[0].strip()
                except IndexError:
                    newsecret = ''
        except (KeyboardInterrupt, EOFError):
            print 'Aborted...'
            sys.exit(0)
        if len(newsecret) < 10:
            print 'Secret must be at least 10 characters long.'
            sys.exit(0)
    elif cipher_type not in ('plain', 'base64'):
        print "unknown cipher_type", cipher_type
        sys.exit(1)
    
    
    if cipher_type == 'blowfish':
        conf['blowfish']['newsecret'] = newsecret
        dry_run or conf.write() # just in case it goes wrong in the middle
    
    pwdb = get_backend()
    
    nb_passwords = 0
    nb_pkeys = 0
    total = 0
    sites = [ pwdb.get_rlogin_site(site['name'])[1]
                                            for site in pwdb.list_sites() ]
    site_done = []
    for siteentry in sites:
        site = siteentry.sid
        if site in site_done:
            continue
        site_done.append(site)
        for rlogin in siteentry.rlogins.values():
            uid = rlogin.uid
            password = rlogin.password
            pkey = rlogin.pkey
        
            # decipher with old secret
            oldpass = decipher(password)
            oldpkey = decipher(pkey)
            # cipher with new secret
            newpass = cipher(oldpass, type=cipher_type, secret=newsecret)
            newpkey = cipher(oldpkey, type=cipher_type, secret=newsecret)
            if ( oldpass != decipher(newpass, secret=newsecret) or
                oldpkey != decipher(newpkey, secret=newsecret) ):
                raise KeyError('Problem with %s cipher on user %s@%s!' %
                                                    (cipher_type, uid, site))
            if dry_run:
                print '-- %s@%s [ %s / %s / %s ]' % (uid, site,
                                                   password, oldpass, newpass)
                print 
            if password != newpass:
                dry_run or pwdb.set_rlogin_password(uid, site, newpass)
                nb_passwords += 1
            if pkey != newpkey:
                dry_run or pwdb.set_rlogin_pkey(uid, site, newpkey)
                nb_pkeys += 1
            total += 1
    
    
    if cipher_type == 'blowfish':
        del conf['blowfish']['newsecret']
        # update secret
        conf['blowfish']['secret'] = newsecret
    conf['sshproxy']['cipher_type'] = cipher_type
    dry_run or conf.write()
    print 'Reciphered %d passwords and %d pkeys on %d entries' % (nb_passwords,
                                                                  nb_pkeys,
                                                                  total)



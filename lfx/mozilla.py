import re, io, http.client, sys

from .util import SANE_SSL_CONTEXT
from .gpg import gpg_verify

__all__ = ['FirefoxVersion', 'get_latest_firefox_version',
           'get_firefox_hash', 'get_firefox_bz2', 'VERSION_RE']

VERSION_RE = '([0-9]+(?:[.][0-9]+)*)'

CDN_HOST = 'download-installer.cdn.mozilla.net'
CDN_DIR = '/pub/firefox/releases/{0}/'
CDN_FIREFOX = 'linux-x86_64/en-US/firefox-{0}.tar.bz2'

VCHECK_HOST = 'download.mozilla.org'
VCHECK_PATH = '/?product=firefox-latest&os=linux&lang=en-US'
VCHECK_REGEXES = [
   re.compile('^[?]product=firefox-{}&os=linux&lang=en-US$'.format(
            VERSION_RE)),
   re.compile(('^http://{}{}{}$'.format(CDN_HOST, CDN_DIR,
     CDN_FIREFOX.replace('x86_64', 'i686'))
               .format(VERSION_RE)))
]

class FirefoxVersion(str):
    __slots__ = []

    def __init__(self, v):
        assert(type(v) is str)
        super().__init__()

    def __lt__(self, other):
        return self.as_sequence() < other.as_sequence()

    def as_sequence(self):
        return tuple(int(v) for v in self.split('.'))

def get_latest_firefox_version():
    conn = http.client.HTTPSConnection(VCHECK_HOST,
                                       context=SANE_SSL_CONTEXT)
    conn.request('get', VCHECK_PATH)
    resp = conn.getresponse()

    if resp.status != 302:
        raise ValueError(resp.status, resp.reason)

    return _location_to_firefox_version(resp.getheader('Location'))
    
def _location_to_firefox_version(location):
    match = None
    for regex in VCHECK_REGEXES:
        match = regex.match(location)
        if match is not None:
            break

    if match is None:
        raise ValueError('Bad Format', location)

    return FirefoxVersion(match.groups()[0])

BLOCK_SIZE = 1048576

def _get_from_cdn(conn, version, filename, callback=lambda: None,
                  block_size=BLOCK_SIZE):
    result = io.BytesIO()

    url = CDN_DIR.format(version) + filename
    print('GET %s ' % url,end='', file=sys.stderr)
    conn.request('GET', url)
    response = conn.getresponse()
    if response.status != 200:
        raise ValueError(response.status, response.reason)

    block = response.read(block_size)
    while block:
        callback()
        result.write(block)
        block = response.read(block_size)

    print(file=sys.stderr)
    result.seek(0)
    return result.getvalue()

def get_firefox_hash(version, keychain):
    conn = http.client.HTTPConnection(CDN_HOST)

    sha512sums = _get_sha512sums(conn, version)
    sha512sums_asc = _get_sha512sums_asc(conn, version)

    if not gpg_verify(sha512sums_asc, sha512sums, keychain):
        raise ValueError('Bad SHA512SUMS signature')

    return 'sha512', _extract_hash(sha512sums, version)

def _get_sha512sums(conn, version):
    return _get_from_cdn(conn, version, 'SHA512SUMS')

def _get_sha512sums_asc(conn, version):
    return _get_from_cdn(conn, version, 'SHA512SUMS.asc')

def _extract_hash(hashlist, version):
    filename = CDN_FIREFOX.format(version).encode('ascii')
    for line in hashlist.split(b'\n'):
        parts = line.strip().split(b' ')
        if len(parts) == 3 and parts[2].strip() == filename:
            return parts[0].strip().decode('ascii')

def get_firefox_bz2(version, callback=lambda: None):
    return _get_from_cdn(http.client.HTTPConnection(CDN_HOST),
                         version, CDN_FIREFOX.format(version),
                         callback)

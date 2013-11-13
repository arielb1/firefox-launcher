#!/usr/bin/env python3

import os, sys, signal, os.path, tempfile, fcntl, time, re
import socket, http.client, ssl, io, hashlib, shutil
from bz2 import BZ2Decompressor

# FIXME
from bz2 import (BZ2Decompressor as Decompressor,
                   BZ2Compressor as Compressor)

from .filekit import TemporaryFileContext, LockFile, AtomicReplacement

sane_ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
sane_ssl_context.verify_mode = ssl.CERT_REQUIRED
sane_ssl_context.set_default_verify_paths()

MAX_VERSION_LENGTH = 65536
MAIN_DIRECTORY = os.path.expanduser('~/firefox-launcher')

if not os.path.exists(MAIN_DIRECTORY):
    os.mkdir(MAIN_DIRECTORY)
if not os.path.isdir(MAIN_DIRECTORY):
    print('launchfirefox: {}: not a directory'.format(MAIN_DIRECTORY),
        file=sys.stderr)
    exit(1)

FIREFOX_ARCHIVE = os.path.join(MAIN_DIRECTORY, 'firefox-latest.tar.xz')
# format: version lastdate
VERSION_FILE = os.path.join(MAIN_DIRECTORY, 'firefox-version')
PROFILE_LOCK = os.path.join(MAIN_DIRECTORY, 'profile.lock')
PROFILE_FILE = os.path.join(MAIN_DIRECTORY, 'profile.tar.xz')
GNUPG_HOME = os.path.join(MAIN_DIRECTORY, 'gnupg')
UPDATE_INTERVAL = 86400

VER_RE = b'([0-9]+(?:[.][0-9]+)*)'
VER_RE_STR = VER_RE.decode('ascii')
DOWNLOAD_HOST = 'download.mozilla.org'
DOWNLOAD_PATH = '/?product=firefox-latest&os=linux&lang=en-US'
DOWNLOAD_RE = re.compile('^[?]product=firefox-{0}&os=linux&lang=en-US$'
                         .format(VER_RE_STR))

CDN_HOST = 'download-installer.cdn.mozilla.net'
CDN_DIR = '/pub/mozilla.org/firefox/releases/{0}/'
CDN_FIREFOX = 'linux-i686/en-US/firefox-{0}.tar.bz2'

DOWNLOAD_RE_CDN = re.compile(('^http://' + CDN_HOST + CDN_DIR + CDN_FIREFOX +
                              '$').format(VER_RE_STR))

TEMP_CONTEXT = TemporaryFileContext(dir=MAIN_DIRECTORY,
                                    suffix='.~{}~'.format(os.getpid()))

def get_sha512_hash_for_release(version):
   conn = http.client.HTTPConnection(CDN_HOST)
   
   print('[-] Downloading SHA512SUMS...',end=' ')
   sys.stdout.flush()
   conn.request('get', CDN_DIR.format(version) + 'SHA512SUMS')
   response = conn.getresponse()
   if response.status != 200:
       print(response.status, response.reason)
       print('COULD NOT UPDATE FIREFOX')
       sys.exit(1)
   sums = response.read()
   print('Done')

   print('[-] Downloading signature and verifying...')
   sys.stdout.flush()
   conn.request('get', CDN_DIR.format(version) + 'SHA512SUMS.asc')
   response = conn.getresponse()
   if response.status != 200:
       print('Got', response.status, response.reason)
       sys.exit(1)
   signature = response.read()

   if not gpg_verify(signature, sums):
       print('Signature verification failed.')
       sys.exit(1)

   download_fn = CDN_FIREFOX.format(version).encode('ascii')
   for line in sums.split(b'\n'):
       parts = line.strip().split(b' ')
       if len(parts) != 3:
           continue
       if parts[2].strip() == download_fn:
           return parts[0]


   print('hash for {} not found - exiting'.format(download_fn))
   sys.exit(1)

def gpg_verify(signature, text):
    rT,wT = os.pipe()
    rS,wS = os.pipe()

    swpid = os.fork()
    if not swpid:
        os.close(rT)
        os.close(wT)
        os.close(rS)
        os.write(wS, signature)
        os._exit(1)
    os.close(wS)

    pid = os.fork()
    if not pid:
        os.close(wT)

        if rT == 3:
            os.dup2(rT,5)
            os.dup2(3,4)
            os.dup2(5,3)
        else:
            os.dup2(rS,3)
            os.dup2(rT,4)
        env = os.environ.copy()
        env['GNUPGHOME'] = GNUPG_HOME

        os.execvpe('gpg', ['gpg', '--verify', '/dev/fd/3', '/dev/fd/4'],
                   env)
        os._exit(1)

    os.close(rS)
    os.close(rT)
    os.write(wT, text)
    os.close(wT)
    
    _,status = os.waitpid(pid, 0)
    _ = os.waitpid(swpid, 0)
    return os.WIFEXITED(status) and not os.WEXITSTATUS(status)

def main():
    try:
        firefox_launcher_pid = os.fork()
        if not firefox_launcher_pid:
            try:
                launch_firefox()
            except IOError:
                os._exit(1)
            os._exit(0)
    except KeyboardInterrupt:
        os._exit(1)

    sys.stdout.flush()

    print('[+] Checking for Updates')
    sys.stdout.flush()

    with LockFile(VERSION_FILE, exclusive=True) as lockfile:
        version_info, update_needed = check_for_updates(lockfile)

        if update_needed:
            print('[+] Updating Firefox')
            os.kill(firefox_launcher_pid, signal.SIGINT)
            with AtomicReplacement(FIREFOX_ARCHIVE, TEMP_CONTEXT) as out:
                update_firefox(version_info, out)
                out.ready = True

        if version_info is not None:
            lockfile.setvalue(format_version(version_info))

    if version_info:
        launch_firefox()

    os.wait()

VERSION_RE = re.compile(b'^([0-9]+(?:[.][0-9]+)*) ' + VER_RE + b'$')

def is_older_then(V, W):
    return [int(v) for v in V.split('.')] < [int(w) for w in W.split('.')]

def check_for_updates(vfile):
    old_version_parts = VERSION_RE.match(vfile.read())

    if old_version_parts:
        old_version, old_time = old_version_parts.groups()
        time_delta = time.time() - float(old_time)
        if time_delta < UPDATE_INTERVAL:
            print('[-] Next check in {} seconds'.format(
                    int(UPDATE_INTERVAL - time_delta)), file=sys.stderr)
            return None, False
    else:
        old_version = b'0'
    old_version = old_version.decode('ascii')

    try:
        print('[-] Checking Latest Version...', end=' ', file=sys.stderr)
        checked_at = time.time()
        sys.stderr.flush()
        conn = http.client.HTTPSConnection(DOWNLOAD_HOST,
                                           context=sane_ssl_context)

        conn.request('get', DOWNLOAD_PATH)
        resp = conn.getresponse()
        if resp.status != 302:
            print(resp.status, resp.reason)
            raise IOError

        loc = DOWNLOAD_RE.match(resp.getheader('Location'))
        if loc is None:
            loc = DOWNLOAD_RE_CDN.match(resp.getheader('Location'))
        if loc is None:
            print('Bad Format')
            raise IOError

        new_version, *_ = loc.groups()
        if is_older_then(old_version, new_version):
            print(new_version)
            return (new_version, checked_at), True
        print()
    except IOError as e:
        print(e)
        print('WARNING: FAILED TO CHECK FOR UPDATES!', file=sys.stderr)

    return (old_version, checked_at), False

def format_version(vers):
    return '{0[0]} {0[1]}\n'.format(vers).encode('ascii')

BLOCK_SIZE = 1048576

def update_firefox(version_info, tfile):
    old,version = version_info
    good_hash = get_sha512_hash_for_release(version)
    bzipped = io.BytesIO()
    scanner = hashlib.sha512()

    print('[-] Downloading Firefox...', end=' ')
    sys.stdout.flush()

    conn = http.client.HTTPConnection(CDN_HOST)
    conn.request('get', (CDN_DIR+CDN_FIREFOX).format(version))
    response = conn.getresponse()
    if response.status != 200:
        print(response.status, response.reason)
        sys.exit(1)

    block = response.read(BLOCK_SIZE)
    while block:
        sys.stdout.write('*')
        sys.stdout.flush()
        
        scanner.update(block)
        bzipped.write(block)
        block = response.read(BLOCK_SIZE)
    bzipped.seek(0)

    if scanner.hexdigest().encode('ascii') != good_hash:
        print('SHA512 Verification Failure')
        sys.exit(1)
    else:
        print(' {}'.format(good_hash.decode('ascii')))

    print('[-] Converting & Storing...', end=' ')
    sys.stdout.flush()

    decom = BZ2Decompressor()
    comp = Compressor()

    block = bzipped.read(BLOCK_SIZE)
    while block:
        tfile.write(comp.compress(decom.decompress(block)))

        sys.stdout.write('*')
        sys.stdout.flush()
        block = bzipped.read(BLOCK_SIZE)

    tfile.write(comp.flush())
    print(' Done')

    print('[-] Finishing...', end=' ')

def save_profile(child_pid):
    pass

def load_profile():
    pass

def unpack_firefox():
    dec = Decompressor()
    arc = open(FIREFOX_ARCHIVE, 'rb')
        
    decompressed = tempfile.NamedTemporaryFile()

    buf = arc.read(BLOCK_SIZE)
    while buf:
        decompressed.write(dec.decompress(buf))
        buf = arc.read(BLOCK_SIZE)
    decompressed.flush()

    shutil.unpack_archive(decompressed.name, format='tar')

have_sigint = False
old_sigint_handler = None

def di():
    global old_sigint_handler
    def _sigint_handler(signo, st):
        global have_sigint
        have_sigint = True
    old_sigint_handler = signal.signal(signal.SIGINT, _sigint_handler)

def ei():
    global old_sigint_handler, have_sigint
    signal.signal(signal.SIGINT, old_sigint_handler)
    old_sigint_handler = None
    if have_sigint:
        have_sigint = False
        raise KeyboardInterrupt
    

def launch_firefox():
    print('[-] Unpacking the Browser... ', end=' ')
    sys.stdout.flush()
    with tempfile.TemporaryDirectory(prefix='firefox-launcher') as direct:
        os.chdir(direct)

        unpack_firefox()
        print('Done')

        print('[-] Loading your Profile... ', end=' ')
        load_profile()
        print('Done')

        print('[-] Launching')
        sys.stdout.flush()
        pid = os.getpid()
        child_pid = -1

        di()
        p = -1
        try:
            child_pid = os.fork()
            ei()

            if child_pid != 0:
                while 1:
                    if os.fork() == 0:
                        save_profile(child_pid)
                        time.sleep(120)
                        os._exit(0)
                    di()
                    p,_ = os.wait()
                    ei()
                    if p == child_pid:
                        try:
                            while 1:
                                os.wait()
                        except OSError:
                            pass
                        save_profile(child_pid)
                        return
        except BaseException:
            if pid != os.getpid(): # All secondary processes
                os._exit(1)

            if p != child_pid: # If child is still alive, kill it
                os.kill(child_pid, signal.SIGINT)

            raise

        env = os.environ
        env['HOME'] = os.getcwd()
        os.chdir('firefox')
        os.execve('./firefox', ['./firefox'], env)
        os._exit(1)

if __name__ == '__main__':
    main()

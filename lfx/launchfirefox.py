#!/usr/bin/env python3

import os, sys, signal, os.path, tempfile, fcntl, time, re
import http.client, io, hashlib, shutil
from bz2 import BZ2Decompressor

# FIXME
from bz2 import (BZ2Decompressor as Decompressor,
                   BZ2Compressor as Compressor)


from . import mozilla
from .filekit import TemporaryFileContext, LockFile, AtomicReplacement
from .gpg import gpg_verify
from .util import ei, di
from .mozilla import VERSION_RE, FirefoxVersion

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

TEMP_CONTEXT = TemporaryFileContext(dir=MAIN_DIRECTORY,
                                    suffix='.~{}~'.format(os.getpid()))

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
        (version, time), update_needed = check_for_updates(lockfile)

        if update_needed:
            print('[+] Updating Firefox')
            os.kill(firefox_launcher_pid, signal.SIGINT)
            with AtomicReplacement(FIREFOX_ARCHIVE, TEMP_CONTEXT) as out:
                update_firefox(version, out)
                out.ready = True

        if version is not None:
            lockfile.setvalue(format_version(version, time))

    p,_ = os.wait()
    assert p == firefox_launcher_pid

    if update_needed:
        launch_firefox()

VERFILE_RE = re.compile(b'^([0-9]+(?:[.][0-9]+)*) ' +
                        VERSION_RE.encode('ascii') + b'$')

def check_for_updates(vfile):
    old_version_parts = VERFILE_RE.match(vfile.read())

    if old_version_parts:
        old_version, old_time = old_version_parts.groups()
        time_delta = time.time() - float(old_time)
        if time_delta < UPDATE_INTERVAL:
            print('[-] Next check in {} seconds'.format(
                    int(UPDATE_INTERVAL - time_delta)), file=sys.stderr)
            return (None, None), False
    else:
        old_version = b'0'
    old_version = FirefoxVersion(old_version.decode('ascii'))

    try:
        print('[-] Checking Latest Version...', end=' ', file=sys.stderr)
        checked_at = time.time()
        sys.stderr.flush()

        new_version = mozilla.get_latest_firefox_version()

        if old_version < new_version:
            print(new_version)
            return (new_version, checked_at), True
        print()
    except IOError as e:
        print(e)
        print('WARNING: FAILED TO CHECK FOR UPDATES!', file=sys.stderr)

    return (old_version, checked_at), False

def format_version(version, time):
    return '{0} {1}\n'.format(version, time).encode('ascii')

BLOCK_SIZE = 1048576

def update_firefox(version, tfile):
    algo, digest = mozilla.get_firefox_hash(version, GNUPG_HOME)
    scanner = hashlib.new(algo)

    print('[-] Downloading Firefox...')
    sys.stdout.flush()

    firefox_bz2 = mozilla.get_firefox_bz2(version,
                                          lambda: (sys.stdout.write('*'),
                                                   sys.stdout.flush()))
    scanner.update(firefox_bz2)

    if scanner.hexdigest() != digest:
        print('SHA512 Verification Failure')
        sys.exit(1)

    print('[-] Converting & Storing...', end=' ')
    sys.stdout.flush()

    decom = BZ2Decompressor()
    comp = Compressor()

    pos = 0
    block = firefox_bz2[pos:pos+BLOCK_SIZE]
    while block:
        sys.stdout.flush()
        tfile.write(comp.compress(decom.decompress(block)))

        sys.stdout.write('*')
        sys.stdout.flush()

        pos+=BLOCK_SIZE
        block = firefox_bz2[pos:pos+BLOCK_SIZE]


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
                    checker = os.fork()
                    if checker == 0:
                        di()
                        save_profile(child_pid)
                        time.sleep(120)
                        os._exit(0)
                    di()
                    p,_ = os.wait()
                    ei()
                    if p == child_pid:
                        try:
                            os.kill(checker, signal.SIGINT)
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

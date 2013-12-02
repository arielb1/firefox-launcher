#!/usr/bin/env python3

import os, sys, signal, os.path, tempfile, fcntl, time, re
import http.client, io, hashlib, shutil

# FIXME
from bz2 import (BZ2Decompressor as Decompressor,
                   BZ2Compressor as Compressor)


from . import mozilla, updater
from .filekit import TemporaryFileContext, LockFile, AtomicReplacement
from .gpg import gpg_verify
from .util import ei, di
from .mozilla import VERSION_RE, FirefoxVersion

BLOCK_SIZE = 1048576
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
    di()
    firefox_launcher_pid = os.fork()
    if not firefox_launcher_pid:
        sys.stdout.flush()
        try:
            ei()
            launch_firefox()
        except (IOError, KeyboardInterrupt):
            os._exit(1)
        os._exit(0)

    try:
        ei()
        n = updater.try_update_firefox(TEMP_CONTEXT, VERSION_FILE,
                                       FIREFOX_ARCHIVE, UPDATE_INTERVAL,
                                       GNUPG_HOME,
                                       lambda: os.kill(firefox_launcher_pid,
                                                       signal.SIGINT))

        if n > 1:
            print('[-] Next Check in', n, 'Seconds', file=sys.stderr)

        di()
    except BaseException:
        print('[-] Failed to check for updates! Shutting down.',
              file=sys.stderr)
        os.kill(firefox_launcher_pid, signal.SIGINT)
        raise

    while 1:
        try:
            p,_ = os.wait()
        except OSError as e:
            os.kill(firefox_launcher_pid, signal.SIGINT)
        else:
            break

    ei()
    assert p == firefox_launcher_pid

    if not n:
        launch_firefox()


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

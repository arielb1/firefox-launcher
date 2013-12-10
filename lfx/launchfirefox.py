#!/usr/bin/env python3

import os, sys, signal, os.path, tempfile
import time, shutil, errno

from .lzma import (LZMADecompressor as Decompressor,
                   LZMACompressor as Compressor)


from . import updater
from .filekit import TemporaryFileContext
from .util import ei, di

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
PROFILE_INTERVAL = 120

TEMP_CONTEXT = TemporaryFileContext(dir=MAIN_DIRECTORY,
                                    suffix='.~{}~'.format(os.getpid()))

def main():
    di()
    firefox_launcher_pid = os.fork()
    if not firefox_launcher_pid:
        sys.stdout.flush()
        try:
            ei()
            launch_firefox(None, FIREFOX_ARCHIVE)
        except (IOError, KeyboardInterrupt):
            os._exit(1)
        os._exit(0)

    try:
        ei()
        with updater.try_update_firefox(TEMP_CONTEXT, VERSION_FILE,
                                        FIREFOX_ARCHIVE, UPDATE_INTERVAL,
                                        GNUPG_HOME) as (updating, ttn):
            if updating:
                os.kill(firefox_launcher_pid, signal.SIGINT)

        if ttn > 1:
            print('[-] Next Check in', ttn, 'Seconds', file=sys.stderr)

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
            assert u.errno == errno.EINTR
            os.kill(firefox_launcher_pid, signal.SIGINT)
        else:
            break

    ei()
    assert p == firefox_launcher_pid

    if updating:
        launch_firefox(None, FIREFOX_ARCHIVE)


def unpack_firefox(archive):
    dec = Decompressor()
    arc = open(archive, 'rb')
        
    decompressed = tempfile.NamedTemporaryFile()

    buf = arc.read(BLOCK_SIZE)
    while buf:
        decompressed.write(dec.decompress(buf))
        buf = arc.read(BLOCK_SIZE)
    decompressed.flush()

    shutil.unpack_archive(decompressed.name, format='tar')

# Should be called with interrupts disabled
# Launches the browser in archive with the profile profile
def launch_firefox(profile, archive):
    print('[-] Unpacking the Browser... ', end=' ')
    sys.stdout.flush()
    with tempfile.TemporaryDirectory(prefix='firefox-launcher') as direct:
        os.chdir(direct)

        unpack_firefox(archive)
        print('Done')

        print('[-] Loading your Profile... ', end=' ')

        print('Done')

        print('[-] Launching')
        sys.stdout.flush()
        start_firefox_in_cwd(profile)

# Starts Firefox in the current directory and takes care of it
def start_firefox_in_cwd(profile):
        pid = os.getpid()
        child_pid = -1

        di()
        try:
            child_pid = os.fork()
 
            if not child_pid:
                env = os.environ
                env['HOME'] = os.getcwd()
                os.chdir('firefox')
                os.execve('./firefox', ['./firefox'], env)
                os._exit(1)
        except BaseException:
            if pid != os.getpid(): # All secondary processes
                os._exit(1)

            raise

        manager_loop(profile, child_pid)

def wait_until(t):
    clock_pid = os.fork()
    if not clock_pid:
        to_sleep = time.time() - t
        if to_sleep > 0:
            time.sleep(to_sleep)
        os._exit(0)

    p,s = os.wait()
    return (None if p == clock_pid else p), s

def manager_loop(profile, child_pid, profile_interval=PROFILE_INTERVAL):
    p = -1
    next_check = time.time() + PROFILE_INTERVAL
    try:
        while p != child_pid:
            p, _ = wait_until(next_check)
            next_check = time.time() + PROFILE_INTERVAL
    finally:
        if p != child_pid:
            os.kill(child_pid, signal.SIGINT)

if __name__ == '__main__':
    main()

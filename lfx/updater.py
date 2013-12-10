import sys, hashlib, io
from contextlib import contextmanager

from bz2 import BZ2Decompressor


from .lzma import (LZMADecompressor as Decompressor,
                   LZMACompressor as Compressor)

from . import mozilla
from .versionfile import VersionFile
from .filekit import AtomicReplacement


def display_asterisk():
    sys.stderr.write('*')
    sys.stderr.flush()

@contextmanager
def try_update_firefox(temp_ctx, lock_name, arc_name, check_interval,
                       gnupg_dir):
    with VersionFile(lock_name, mozilla.FirefoxVersion,
                     check_interval) as vers:
        time_to_next = vers.can_skip_updates()
        if time_to_next:
            yield (False, time_to_next)
            return

        print('[-] Checking Firefox Version...', end=' ', file=sys.stderr)
        latest = mozilla.get_latest_firefox_version()
        print(latest, file=sys.stderr)

        if vers.register_update(latest):
            yield (True, 0)
            with AtomicReplacement(arc_name, temp_ctx) as out:
                print('[+] Updating Firefox', file=sys.stderr)
                update_firefox(latest, out, gnupg_dir)
                out.ready = True
        else:
            yield (False, 1)

def update_firefox(version, out, gnupg_dir):
    bz2_archive = get_bz2_archive(version, gnupg_dir)
    print('[-] Converting & Storing...', end=' ', file=sys.stderr)
    write_fx_archive(bz2_archive, out)
    print(' Done', file=sys.stderr)

def get_bz2_archive(version, gnupg_dir):
    algo, digest = mozilla.get_firefox_hash(version, gnupg_dir)
    scanner = hashlib.new(algo)

    firefox_bz2 = mozilla.get_firefox_bz2(version, display_asterisk)
    scanner.update(firefox_bz2)
    if scanner.hexdigest() != digest:
        raise ValueError('Hash Verification Failure', scanner.hexdigest(),
                         digest)

    return firefox_bz2

BLOCK_SIZE = 1048576
def write_fx_archive(firefox_bz2, out):
    decom = BZ2Decompressor()
    comp = Compressor()

    firefox_bz2_f = io.BytesIO(firefox_bz2)
    def decompress():
        decompressed = firefox_bz2_f.read(BLOCK_SIZE)
        # BZip2 crashes when decompressing empty string after EOS
        return decom.decompress(decompressed) if decompressed else ''
    comp.compress_pump(decompress, out.write, display_asterisk)
    out.write(comp.flush())

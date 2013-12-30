import os, os.path, tarfile, io, re

from .filekit import LockFile, AtomicReplacement
from .lzma import LZMACompressor, LZMADecompressor, FILTER_DELTA
from .lzma import FILTER_DELTA2

PARTFILE_RE = re.compile('^profile.([0-9]+).tar.lzD$')

LOCKFILE_NAME = 'profile.lock'
PARTFILE_NAME = 'profile.{}.tar.lzD'
COMPLETE_NAME = 'profile.complete.tar.lzD'

# Assumes firefox is at cwd
class FirefoxProfile:
    def __init__(self, profile_dir, temp_ctx, feedback_fun, block_size):
        self.profile_dir = profile_dir
        self.temp_ctx = temp_ctx
        self.compressor = None
        self.lockfile = None
        self.next_partfile = 0
        self.block_size = block_size
        self.feedback_fun = feedback_fun
        self.last_profile = None

    def __enter__(self):
        if not os.path.exists(self.profile_dir):
            os.mkdir(self.profile_dir)

        self.lockfile = LockFile(os.path.join(self.profile_dir,
                                              LOCKFILE_NAME),
                                 exclusive=True).__enter__()
        return self

    def load(self):
        self.last_profile = io.BytesIO()
        self._load_profile(LZMADecompressor(filter=FILTER_DELTA2))
        self.coalesce()
        self._extract_profile()

    def partfile_name(self, i):
        return os.path.join(self.profile_dir, PARTFILE_NAME.format(i))

    def complete_name(self):
        return os.path.join(self.profile_dir, COMPLETE_NAME)

    def _load_profile(self, dec):
        if os.path.exists(self.complete_name()):
            complete_file = open(self.complete_name(), 'rb')
            dec.decompress_pump(lambda: complete_file.read(self.block_size),
                                self.last_profile.write, self.feedback_fun)
        else:
            last = 0
            while os.path.exists(self.partfile_name(last)):
                self.last_profile.seek(0)
                self.last_profile.truncate()
                cur_file = open(self.partfile_name(last), 'rb')
                dec.decompress_pump(lambda: cur_file.read(self.block_size),
                                    self.last_profile.write,
                                    self.feedback_fun)
                last += 1
        self.last_profile.seek(0)

    def coalesce(self):
        self.compressor = LZMACompressor(filter=FILTER_DELTA2)
        with AtomicReplacement(self.complete_name(), self.temp_ctx) as rep:
            self.compressor.compress_pump(
                lambda: self.last_profile.read(self.block_size),
                rep.write, self.feedback_fun)
            rep.write(self.compressor.sync())
            rep.ready = True

        for f in os.listdir(self.profile_dir):
            if PARTFILE_RE.match(f):
                os.unlink(os.path.join(self.profile_dir, f))

        os.rename(self.complete_name(), self.partfile_name(0))
        self.next_partfile = 1
        self.last_profile.seek(0)

    def _extract_profile(self):
        try:
            tar = tarfile.open(fileobj=self.last_profile)
            tar.extractall()
        except tarfile.ReadError: # tar also crashes on empty file
            pass
        self.last_profile.seek(0)

    def __exit__(self, ex, et, tb):
        return self.lockfile.__exit__(ex, et, tb)

    def snapshot_profile(self):
        out = io.BytesIO()
        tar = tarfile.open(fileobj=out, mode='w')
        if os.path.exists('.fontconfig'):
            tar.add('.fontconfig')
        if os.path.exists('.mozilla'):
            tar.add('.mozilla')
        tar.close()
        out.seek(0)
        self.last_profile = out

    def write_profile(self):
        with AtomicReplacement(self.partfile_name(self.next_partfile),
                               self.temp_ctx) as rep:
            self.compressor.compress_pump(
                lambda: self.last_profile.read(self.block_size),
                rep.write, self.feedback_fun)
            rep.write(self.compressor.sync())
            rep.ready = True
        self.last_profile.seek(0)
        self.next_partfile += 1

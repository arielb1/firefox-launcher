import os, os.path, tarfile, io, re

from .filekit import LockFile, AtomicReplacement
from .lzma import LZMACompressor, LZMADecompressor, FILTER_DELTA

PARTFILE_RE = re.compile('^profile.([0-9]+).tar.lzD$')

LOCKFILE_NAME = 'profile.lock'
PARTFILE_NAME = 'profile.{}.tar.lzD'
COMPLETE_NAME = 'profile.complete.tar.lzD'

class FirefoxProfile:
    def __init__(self, profile_dir, firefox_dir, temp_ctx,
                 feedback_fun, block_size):
        self.profile_dir = profile_dir
        self.firefox_dir = firefox_dir
        self.temp_ctx = temp_ctx
        self.profile_snapshot = None
        self.compressor = None
        self.lockfile = None
        self.next_partfile = 0
        self.block_size = block_size
        self.feedback_fun = feedback_fun

    def __enter__(self):
        if not os.path.exists(self.profile_dir):
            os.mkdir(self.profile_dir)

        self.lockfile = LockFile(os.path.join(self.profile_dir,
                                              LOCKFILE_NAME),
                                 exclusive=True).__enter__()
        return self

    def load(self):
        self.compressor = LZMACompressor(FILTER_DELTA)
        profile_data = io.BytesIO()
        self._load_profile(profile_data, LZMADecompressor(FILTER_DETA))
        profile_data.seek(0)
        self._setup_profile(profile_data)
        profile_data.seek(0)
        self._extract_profile(profile_data)

    def partfile_name(self, i):
        return os.path.join(self.profile_dir, PARTFILE_NAME.format(i))

    def complete_name(self):
        return os.path.join(self.profile_dir, COMPLETE_NAME)

    def _load_profile(self, out, dec):
        if os.path.exists(self.complete_name()):
            complete_file = open(self.complete_name(), 'rb')
            dec.decompress_pump(lambda: complete_file.read(self.block_size),
                                out.write, self.feedback_fun)
        else:
            last = 0
            while os.path.exists(self.partfile_name(last)):
                out.seek(0)
                out.truncate()
                cur_file = open(self.partfile_name(last), 'rb')
                dec.decompress_pump(lambda: cur_file.read(self.block_size),
                                    out.write, self.feedback_fun)
                last += 1

    def _setup_profile(self, out):
        with AtomicReplacement(self.complete_name(), self.temp_ctx) as rep:
            self.compressor.compress_pump(lambda: out.read(self.block_size),
                                          rep.write, self.feedback_fun)
            rep.ready = True

        for f in os.listdir(self.profile_dir):
            if PARTFILE_RE.match(f):
                os.unlink(f)

        os.rename(self.complete_name(), self.partfile_name(0))
        self.next_partfile = 1

    def _extract_profile(self, out):
        tar = tarfile.open(fileobj=out)
        tar.extractall()

    def __exit__(self, ex, et, tb):
        return self.lockfile.__exit__(ex, et, tb)

    def snapshot_profile(self):
        out = io.BytesIO()
        tar = tarfile.open(fileobj=out, mode='w')
        tar.add('.fontconfig')
        tar.add('.mozilla')
        out.seek(0)
        return out

    def write_profile(self, snapshot):
        with AtomicReplacement(self.partfile_name(next_partfile),
                               self.temp_ctx) as rep:
            self.compressor.compress_pump(lambda: out.read(self.block_size),
                                          rep.write, self.feedback_fun)
            rep.ready = True
        self.next_partfile += 1

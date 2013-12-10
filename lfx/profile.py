import os.path, tarfile, io

from .filekit import LockFile
from .lzma import LZMACompressor, LZMADecompressor

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
        profile_data = io.BytesIO()
        self._load_profile(profile_data)
        profile_data.seek(0)
        self._cleanup_profile(profile_data)
        profile_data.seek(0)
        self._extract_profile(profile_data)

    def _load_profile(self):
        complete_file_name = os.path.join(self.profile_dir, COMPLETE_NAME)

        if os.path.exists(complete_file_name):
            complete_file = open(complete_file_name, 'rb')
            

    def __exit__(self, ex, et, tb):
        return self.lockfile.__exit__(ex, et, tb)

    def snapshot_profile(self):
        pass

    def write_profile(self):
        pass

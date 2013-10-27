import os
from os import O_RDONLY, O_WRONLY, O_CREAT, O_RDWR
from fcntl import lockf, LOCK_SH, LOCK_EX
from io import BytesIO
import tempfile

__all__ = ['TemporaryFileContext', 'LockFile', 'AtomicReplacement']

BLOCK_SIZE = 1048576

class TemporaryFileContext:
    def __init__(self, suffix='', prefix='tmp', dir=None):
        self.suffix = suffix
        self.prefix = prefix
        self.dir = dir

    def mkstemp(self):
        return tempfile.NamedTemporaryFile(suffix=self.suffix,
                                           prefix=self.prefix,
                                           dir=self.dir)

    def mkdtemp(self):
        return tempfile.TemporaryDirectory(suffix=self.suffix,
                                           prefix=self.prefix,
                                           dir=self.dir)

# Returns result in BYTES!
class LockFile:
    def __init__(self, path, exclusive=False):
        self.path = path
        self.exclusive = exclusive
        self.refcount = 0
        self.fd = -1
        self.out_content = None
        self.in_content = None

    def read(self):
        if self.fd == -1:
            raise ValueError('IO operation on a closed file')

        if self.in_content is None:
            out = BytesIO()

            buf = os.read(self.fd, BLOCK_SIZE)
            while buf:
                out.write(buf)
                buf = os.read(self.fd, BLOCK_SIZE)
                os.lseek(self.fd, 0, 0)

            self.in_content = out.getvalue()

        return self.in_content

    def setvalue(self, value):
        if not self.exclusive:
            raise ValueError('Must lock exclusively before writing!')

        self.out_content = value

    def __enter__(self):
        if self.fd != -1:
            return

        openflags = O_CREAT | (O_RDWR if self.exclusive else O_WRONLY)
        lockflags = LOCK_EX if self.exclusive else LOCK_SH

        self.fd = os.open(self.path, openflags)
        self.refcount += 1

        lockf(self.fd, lockflags)
        return self

    def __exit__(self, e_t, e_v, tb):
        self.refcount -= 1

        if self.fd == -1:
            return

        if self.out_content is not None:
            os.ftruncate(self.fd, 0)
            os.write(self.fd, self.out_content)
            self.out_content = None

        if self.refcount == 0:
            os.close(self.fd)
            self.fd = -1

class AtomicReplacement:
    def __init__(self, path, tctx):
        self.path = path
        self.tempfile_context = tctx
        self.ready = False
        self.tempfile = None

    def __enter__(self):
        self.tempfile = self.tempfile_context.mkstemp().__enter__()
        return self

    def write(self, data):
        self.tempfile.write(data)

    def __exit__(self, e_t, e_v, tb):
        if self.ready:
            self.tempfile.delete = False
            name = self.tempfile.name
            result = self.tempfile.__exit__(e_t, e_v, tb)

            try:
                os.rename(name, self.path)
            except OSError as e:
                os.unlink(name)
                raise
            return result

        return self.tempfile.__exit__(e_t, e_v, tb)

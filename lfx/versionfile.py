
from .filekit import LockFile
import time

class VersionFile:
      def __init__(self, fn, version_parser, check_interval):
            self.fn, self.check_interval = fn, check_interval
            self.version_parser = version_parser
            self.version = self.check_time = None
            self.lockf = None

      def __enter__(self):
            self.lockf = LockFile(self.fn, True).__enter__()
            return self

      def __exit__(self, et, ex, tb):
            if self.check_time is not None and ex is None:
                  self.lockf.setvalue('{} {}\n'.format(self.version,
                                      self.check_time).encode('utf-8'))
            return self.lockf.__exit__(et, ex, tb)

      def can_skip_updates(self):
            '''\
Returns falsey if updates can be skipped, or number of seconds before
    next update otherwise.

Must be called before receive_update.
'''
            version_s, time_s = self.lockf.read().decode(
                  'utf-8').strip().split(' ')
            cur_time = time.time()
            if cur_time - float(time_s) < self.check_interval:
                  return self.check_interval - (cur_time - float(time_s))
            self.version = version_s
            self.check_time = cur_time
            return 0

      def register_update(self, newversion):
            '''\
Returns True if the new version is an update, False otherwise.
Also updates the version saved on scope exit.
'''
            if newversion > self.version_parser(self.version):
                  self.version = newversion
                  return True
            return False

import os
import ctypes


class _DirectoryFD:
    opened = False

    def __init__(self, fd):
        self._dir_fd = fd
        self.opened = True

    def close(self):
        if self.opened:
            self.opened = False
            os.close(self._dir_fd)

    def fileno(self):
        return self._dir_fd

    def _opener(self, path, flags):
        return os.open(path, flags, dir_fd=self._dir_fd)

    def open(self, path, mode):
        return open(path, mode=mode, opener=self._opener)

    def stat(self, path):
        return os.stat(path, dir_fd=self._dir_fd)

    def listdir(self):
        return os.listdir(self._dir_fd)

    @property
    def closed(self):
        return self.opened


def fd_for_dir(path, dir_fd=None):
    return _DirectoryFD(
        os.open(path,
                flags=os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                dir_fd=dir_fd))


def opendir(path):
    return fd_for_dir(path)


def fdopendir(fd, path):
    return fd_for_dir(path, fd)


INITMODULEFUNC = ctypes.PYFUNCTYPE(ctypes.py_object)

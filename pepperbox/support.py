import errno
import os


class directory(object):
    """An object representing a directory handle.
    Can be used as a context manager, that closes the dir handle on exit.
    Supports the fileno function (returning an fd) like file objects.
    """

    def __init__(self, dirfd, name=None):
        if not isinstance(dirfd, int):
            raise ValueError('not an integer (file descriptor)')
        self._dirfd = dirfd
        self._name = name
        self._open = True

    def fileno(self):
        if self.closed:
            raise ValueError('I/O operation on closed directory')
        return self._dirfd

    # alias fileno to dirno
    dirno = fileno

    def _opener(self, path, flags):
        return os.open(path, flags, dir_fd=self.fileno())

    def open(self, path, mode='r'):
        assert not set(mode) & set('wa+')
        return open(path, mode=mode, opener=self._opener)

    def opendir(self, path):
        return _opendir(path,
                        func=os.partial(os.open,
                                        dir_fd=self.fileno()))

    def lstat(self, path):
        return os.stat(path, dir_fd=self.fileno())

    def exists(self, path):
        try:
            self.lstat(path)
        except OSError as e:
            if e.errno == errno.ENOENT:
                return False
            raise
        return True

    def close(self):
        """Close the open directory handle"""
        if self._open:
            os.close(self._dirfd)
            self._open = False

    def __enter__(self):
        """Enter the ctx manager - returns itself"""
        return self

    def __exit__(self, errtype, errval, errtb):
        """Exit the ctx manager, closing the handle"""
        self.close()

    @property
    def closed(self):
        """Returns true if handle is closed"""
        return not self._open

    @property
    def name(self):
        """Returns handle name/path"""
        return self._name

    def listdir(self, _fs=None):
        """Return directory contents in a list for current handle.
        """
        return os.listdir(self._dirfd)


def _opendir(path, func):
    flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    return directory(func(path, flags), path)


def opendir(path):
    return _opendir(path, func=os.open)

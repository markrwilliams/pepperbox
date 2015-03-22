import errno
import functools
import os
import stat


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

    def handle_abspath(self, path):
        if not path.startswith('/'):
            return path

        if not path.startswith(self.name):
            raise ValueError("path {} not a child of {}".format(path,
                                                                self.name))
        path = path.replace(self.name, '')
        if path.startswith('/'):
            path = path[1:]
        return path

    def open(self, path, mode='r'):
        assert not set(mode) & set('wa+')
        path = self.handle_abspath(path)
        return open(path, mode=mode, opener=self._opener)

    def opendir(self, path):
        return _opendir(self.handle_abspath(path),
                        func=functools.partial(os.open,
                                               dir_fd=self.fileno()),
                        abspath=path)

    def lstat(self, path):
        path = self.handle_abspath(path)
        return os.stat(path, dir_fd=self.fileno())

    def isfile(self, path):
        try:
            st = self.lstat(path)
        except (OSError, ValueError):
            return False
        return stat.S_ISREG(st.st_mode)

    def isdir(self, path):
        try:
            st = self.lstat(path)
        except (OSError, ValueError):
            return False
        return stat.S_ISDIR(st.st_mode)

    def exists(self, path):
        try:
            self.lstat(path)
        except (OSError, ValueError) as e:
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

    def listdir(self,):
        """Return directory contents in a list for current handle.
        """
        return os.listdir(self._dirfd)


def _opendir(path, func, abspath=None):
    flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    return directory(func(path, flags), abspath or path)


def opendir(path):
    return _opendir(path, func=os.open)

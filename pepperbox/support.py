import errno
import os
from fsnix import fs, util


class file_with_name:

    def __init__(self, fileinst, name):
        self.fileinst = fileinst
        self.name = name

    def __getattr__(self, attr):
        return getattr(self.fileinst, attr)


class directory(util.directory):

    def open(self, path, mode='r'):
        assert not set(mode) & set('wa+')
        fd = fs.openat(self.fileno(), path, os.O_RDONLY)
        name = os.path.join(self.name, path)
        return file_with_name(os.fdopen(fd, mode), name)

    def opendir(self, path):
        return fopendirat(self.fileno(), path)

    def lstat(self, path):
        return fs.fstatat(self.fileno(), path)

    def exists(self, path):
        try:
            self.lstat(path)
        except OSError as e:
            if e.errno == errno.ENOENT:
                return False
            raise
        return True


def _opendir(path, func):
    flags = (os.O_RDONLY | os.O_DIRECTORY)
    if fs.O_CLOEXEC:
        # if O_CLOEXEC is available use it: prevents race conditions
        # in threaded applications
        flags |= fs.O_CLOEXEC
        fd = func(path, flags)
    else:
        fd = util.setfdcloexec(func(path, flags))
    return directory(fd, path)


def opendir(path):
    return _opendir(path, func=os.open)


def fopendirat(fd, path):
    return _opendir(path,
                    func=lambda *args, **kwargs:
                    fs.openat(fd, *args, **kwargs))
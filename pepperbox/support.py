import os
import stat

import sys


if sys.version_info.major > 2:
    from .py34 import support
else:
    from .py27 import support


class BadPath(Exception):
    pass


class BadMode(Exception):
    pass


class DirectoryFD(object):

    def __init__(self, path, dirobj=None):
        self.name = path
        self._dirobj = dirobj or support.opendir(path)
        self.fileno = self._dirobj.fileno

    def handle_abspath(self, path):
        path = os.path.normpath(path)
        if not os.path.isabs(path):
            return path

        if not path.startswith(self.name):
            raise BadPath("path {} not a child of {}".format(path,
                                                             self.name))
        path = path.replace(self.name, '')
        if os.path.isabs(path):
            path = path[1:]

        return path or '.'

    def open(self, path, mode='rb'):
        bad = set('wa+') & set(mode)
        if bad:
            raise BadMode('invalid mode components {!r}'.format(bad))

        path = self.handle_abspath(path)
        return self._dirobj.open(path, mode)

    def opendir(self, path):
        path = self.handle_abspath(path)
        return DirectoryFD(os.path.join(self.name, path),
                           support.fdopendir(self._dirobj.fileno(),
                                             path))

    def stat(self, path):
        path = self.handle_abspath(path)
        return self._dirobj.stat(path)

    def _quiet_stat(self, path):
        try:
            return self.stat(path)
        except (OSError, BadPath):
            return None

    def exists(self, path):
        return bool(self._quiet_stat(path))

    def isfile(self, path):
        st = self._quiet_stat(path)
        return st and stat.S_ISREG(st.st_mode)

    def isdir(self, path):
        st = self._quiet_stat(path)
        return st and stat.S_ISDIR(st.st_mode)

    def listdir(self):
        return self._dirobj.listdir()

    def close(self):
        self._dirobj.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    @property
    def closed(self):
        return self._dirobj.closed

    def __del__(self):
        self.close()


class BaseOpenatFileFinder(object):

    def __init__(self, path, rights):
        self.path = path
        self.dirobj = DirectoryFD(path)
        for rightsObj in rights:
            rightsObj.limitFile(self.dirobj)

    def dirobjs_from_path(self, path):
        if path:
            dirobjs = []
            for p in path:
                try:
                    dirobj = self.dirobj.opendir(p)
                except BadPath:
                    return []
                dirobjs.append(dirobj)
            return dirobjs
        else:
            return [self.dirobj]

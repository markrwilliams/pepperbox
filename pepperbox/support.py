import ctypes
import os
import stat
import sys


def generate_py_tag():
    """like sys.implementation.cache_tag, except:

    1) it's in Python 2

    2) it's a valid Python identifier, so it can be used in module names

    https://www.python.org/dev/peps/pep-0421/#required-attributes
    """

    if hasattr(sys, 'implementation'):
        name = sys.implementation.name
    elif hasattr(sys, 'subversion'):
        name, _, _ = sys.subversion
    else:
        raise RuntimeError("Could not discover interpreter name")

    name = name.lower()
    version = '{}{}'.format(*sys.version_info[:2])

    return '{}_{}'.format(name, version)


PY_TAG = generate_py_tag()


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


class _Py_PackageContext(object):
    """A ctypes implementation of _Py_PackageContext switching, which
    necessary for loading extension modules with fully qualified
    names:

    "Make sure name is fully qualified.

    This is a bit of a hack: when the shared library is loaded,
    the module name is "package.module", but the module calls
    Py_InitModule*() with just "module" for the name.  The shared
    library loader squirrels away the true name of the module in
    _Py_PackageContext, and Py_InitModule*() will substitute this
    (if the name actually matches)."

    See:
    https://hg.python.org/releasing/2.7.9/file/753a8f457ddc/Python/modsupport.c#l49

    :param fullname: the full name, including parent packages, if any,
    of the extension module about to be loaded

    :param shortname: the name of the module being loaded, without any
    parent packages.

    """

    _Py_PackageContext = ctypes.c_char_p.in_dll(ctypes.pythonapi,
                                                '_Py_PackageContext')

    def __init__(self, fullname, shortname):
        self.fullname = fullname
        self.shortname = shortname

    def __enter__(self):
        self.oldpackagecontext = self._Py_PackageContext.value
        if self.fullname != self.shortname:
            self._Py_PackageContext.value = self.fullname

    def __exit__(self, *exc_info):
        self._Py_PackageContext.value = self.oldpackagecontext


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

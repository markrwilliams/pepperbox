# cribbed from fsnix's source and http://pymotw.com/2/sys/imports.html
import gc
import errno
import imp
import os
import sys
import struct
import marshal
from pepperbox._ffi import fdlopen, RTLD_NOW, dlsym, callable_with_gil
from pepperbox.support import opendir


class OpenatLoader(object):
    def __init__(self, path_entry, dirobj, relpath, is_package):
        self.path_entry = path_entry
        self.dirobj = dirobj
        self.relpath = relpath
        self._is_package = is_package

    def get_data(self, fullname):
        raise IOError

    def is_package(self, fullname):
        return self._is_package

    def get_code(self, fullname):
        raise IOError

    def get_source(self, fullname):
        raise IOError

    def _populate_module(self, module, fullname):
        return module

    def load_module(self, fullname):
        if fullname in sys.modules:
            module = sys.modules[fullname]
        else:
            module = imp.new_module(fullname)
        _, _, shortname = fullname.rpartition('.')

        module.__file__ = self.relpath
        module.__name__ = fullname
        module.__loader__ = self
        module.__package__ = '.'.join(fullname.split('.')[:-1])

        if self._is_package:
            module.__path__ = [self.path_entry]

        module = self._populate_module(module, fullname, shortname)
        sys.modules[fullname] = module
        return module


class PyOpenatLoader(OpenatLoader):

    def _populate_module(self, module, fullname, shortname):
        try:
            with self.dirobj.open(self.relpath) as f:
                module.__file__ = f.name
                src = f.read()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            raise ImportError(e)

        exec src in module.__dict__

        return module


class PyCompiledOpenatLoader(OpenatLoader):
    # native order
    MARSHAL_LONG = struct.Struct('I')
    (MAGIC,) = MARSHAL_LONG.unpack(imp.get_magic())

    fileobj = None

    def _read_marshal_long(self, f):
        try:
            return self.MARSHAL_LONG.unpack(f.read(self.MARSHAL_LONG.size))[0]
        except struct.error:
            return None

    def _ensure_mtime_ok(self, mtime):
        uncompiled = self.relpath.replace('.pyc', '.py')
        try:
            stat = self.dirobj.lstat(uncompiled)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
        else:
            # compare only lowest 4 bytes
            if int(stat.st_mtime) & 0xFFFFFFFF != mtime:
                raise ImportError

    def load_module(self, fullname):
        try:
            with self.dirobj.open(self.relpath) as f:
                self.fileobj = f
                magic = self._read_marshal_long(f)
                if magic is None or magic != self.MAGIC:
                    raise ImportError('Bad magic number in '
                                      '{}'.format(self.relpath))
                mtime = self._read_marshal_long(f)
                if mtime is None:
                    raise EOFError

                self._ensure_mtime_ok(mtime)
                return super(PyCompiledOpenatLoader,
                             self).load_module(fullname)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            raise ImportError(e)

    def _populate_module(self, module, fullname, shortname):
        exec marshal.load(self.fileobj) in module.__dict__
        return module


class TryPycThenPyOpenatLoader(object):

    def __init__(self, *args, **kwargs):
        self.pyc_loader = PyCompiledOpenatLoader(*args, **kwargs)
        self.py_loader = PyOpenatLoader(*args, **kwargs)
        self.pyc_loader.relpath = self.py_loader.relpath.replace('.py', '.pyc')

    def __getattr__(self, attr):
        return getattr(self.py_loader, attr)

    def load_module(self, *args, **kwargs):
        try:
            return self.pyc_loader.load_module(*args, **kwargs)
        except:
            return self.py_loader.load_module(*args, **kwargs)


class RTLDOpenatLoader(OpenatLoader):

    def _populate_module(self, module, fullname, shortname):
        gc.disable()
        try:
            with self.dirobj.open(self.relpath) as so:
                so_fd = so.fileno()
                loaded_so = fdlopen(so_fd, RTLD_NOW)
                initmodule_pointer = dlsym(loaded_so, 'init%s' % shortname)
                initmodule = callable_with_gil(initmodule_pointer)
                initmodule()
                return sys.modules[fullname]
        finally:
            gc.enable()


class OpenatFinder(object):
    SUFFIXES = tuple(imp.get_suffixes())

    def __init__(self, path_entry, rights=None):
        if not os.path.isdir(path_entry):
            raise ValueError('{!r} is not a path entry'.format(path_entry))

        self.path_entry = path_entry
        self.directory = opendir(path_entry)
        if rights is not None:
            rights.limitFile(self.directory)

    def __call__(self, path_entry):
        if self.path_entry != path_entry:
            raise ImportError

    def __str__(self):
        return '<{} for {}">'.format(self.__class__.__name__, self.path_entry)

    def _find_loader(self, dirobj, fullname):
        _, _, module = fullname.rpartition('.')

        if imp.is_builtin(fullname):
            return None

        for suffix, mode, kind in self.SUFFIXES:
            for additional, is_package in [((), False),
                                           (('__init__',), True)]:
                relpath = os.path.join(module, *additional) + suffix
                if dirobj.exists(relpath):
                    break
            else:
                continue

            if kind == imp.C_EXTENSION:
                loader = RTLDOpenatLoader
            elif kind == imp.PY_SOURCE:
                loader = TryPycThenPyOpenatLoader
            elif kind == imp.PY_COMPILED:
                loader = PyCompiledOpenatLoader
            return loader(self.path_entry, dirobj, relpath, is_package)

    def find_module(self, fullname, path=None):
        if path:
            dirobjs = []
            for p in path:
                if not p.startswith(self.path_entry):
                    return None
                p = p.replace(self.path_entry, '')
                if p.startswith('/'):
                    p = p[1:]
                dirobj = self.directory.opendir(p)
                dirobjs.append(dirobj)
        else:
            dirobjs = [self.directory]

        for dirobj in dirobjs:
            loader = self._find_loader(dirobj, fullname)
            if loader:
                return loader


def install(rights, preimports=()):
    for preimport in preimports:
        __import__(preimport)

    for entry in sys.path:
        if os.path.isdir(entry):
            sys.meta_path.append(OpenatFinder(entry, rights))

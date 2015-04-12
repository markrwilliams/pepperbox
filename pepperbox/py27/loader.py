# cribbed from fsnix's source and http://pymotw.com/2/sys/imports.html
import gc
import errno
import imp
import os
import sys
import struct
import marshal
from .._ffi import fdlopen, RTLD_NOW, dlsym, make_callable_with_gil
from ..support import BaseOpenatFileFinder
from .support import INITMODULEFUNC

callable_with_gil = make_callable_with_gil(INITMODULEFUNC)


class OpenatLoader(object):
    def __init__(self, dirobj, relpath, is_package):
        self.dirobj = dirobj
        self.relpath = relpath
        self._is_package = is_package

    def is_package(self, fullname):
        return self._is_package

    def _populate_module(self, module, fullname):  # pragma: no cover
        raise NotImplementedError

    def load_module(self, fullname):
        if fullname in sys.modules:
            module = sys.modules[fullname]
        else:
            module = imp.new_module(fullname)

        package, _, module_name = fullname.rpartition('.')

        module.__file__ = os.path.join(self.dirobj.name, self.relpath)
        module.__name__ = fullname

        if self._is_package:
            module.__package__ = module_name
            module.__path__ = [os.path.join(self.dirobj.name, module_name)]
        else:
            module.__package__ = package or None

        sys.modules[fullname] = module = self._populate_module(module,
                                                               fullname,
                                                               module_name)

        return module


class PyOpenatLoader(OpenatLoader):

    def _populate_module(self, module, fullname, shortname):
        sys.modules[fullname] = module
        try:
            with self.dirobj.open(self.relpath) as f:
                src = f.read()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            raise ImportError(e)

        exec src in module.__dict__

        return module


class LoadCompiledModuleFailure(Exception):

    def __init__(self, real_exc):
        super(LoadCompiledModuleFailure, self).__init__()
        self.real_exc = real_exc


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
            stat = self.dirobj.stat(uncompiled)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise LoadCompiledModuleFailure(e)
        else:
            # compare only lowest 4 bytes
            if int(stat.st_mtime) & 0xFFFFFFFF != mtime:
                raise LoadCompiledModuleFailure(ImportError())

    def wrapped_load_module(self, fullname):
        try:
            with self.dirobj.open(self.relpath) as f:
                self.fileobj = f
                magic = self._read_marshal_long(f)
                if magic is None or magic != self.MAGIC:
                    raise LoadCompiledModuleFailure(
                        ImportError('Bad magic number in '
                                    '{}'.format(self.relpath)))
                mtime = self._read_marshal_long(f)
                if mtime is None:
                    raise LoadCompiledModuleFailure(EOFError())

                self._ensure_mtime_ok(mtime)
                return super(PyCompiledOpenatLoader,
                             self).load_module(fullname)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise LoadCompiledModuleFailure(e)
            raise LoadCompiledModuleFailure(ImportError(e))

    def load_module(self, fullname):
        try:
            return self.wrapped_load_module(fullname)
        except LoadCompiledModuleFailure as e:
            raise e.real_exc

    def _populate_module(self, module, fullname, shortname):
        sys.modules[fullname] = module
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
            return self.pyc_loader.wrapped_load_module(*args, **kwargs)
        except LoadCompiledModuleFailure:
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


class OpenatFileFinder(BaseOpenatFileFinder):
    SUFFIXES = tuple(imp.get_suffixes())

    def __call__(self, path):
        if self.path != path:
            raise ImportError

    def __str__(self):
        return '<{} for {}">'.format(self.__class__.__name__, self.path)

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
            return loader(dirobj, relpath, is_package)

    def find_module(self, fullname, path=None):
        for dirobj in self.dirobjs_from_path(path):
            loader = self._find_loader(dirobj, fullname)
            if loader:
                return loader

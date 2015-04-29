# cribbed from fsnix's source and http://pymotw.com/2/sys/imports.html
import gc
import errno
import imp
import os
import sys
import struct
import marshal
from .._ffi import fdlopen, RTLD_NOW, dlsym, make_callable_with_gil
from .support import INITMODULEFUNC
from ..support import BaseOpenatFileFinder, _Py_PackageContext

callable_with_gil = make_callable_with_gil(INITMODULEFUNC)

MODULE_TYPE_TUPLES = tuple(imp.get_suffixes())
SUFFIXES = {suffix for suffix, _, _ in MODULE_TYPE_TUPLES}


class OpenatLoader(object):
    def __init__(self, fullname, path, dirobj):
        self.name = fullname
        self.path = path
        self.dirobj = dirobj

    def get_filename(self, fullname):
        return self.path

    def is_package(self, fullname):
        basename = os.path.basename(self.get_filename(fullname))
        name, ext = os.path.splitext(basename)
        return ext in SUFFIXES and name == '__init__'

    def _populate_module(self, module, fullname,
                         shortname):  # pragma: no cover
        raise NotImplementedError

    def load_module(self, fullname):
        if fullname in sys.modules:
            module = sys.modules[fullname]
        else:
            sys.modules[fullname] = module = imp.new_module(fullname)

        package, _, module_name = fullname.rpartition('.')

        module.__file__ = self.path
        module.__name__ = fullname

        if self.is_package(fullname):
            module.__path__ = [os.path.join(self.dirobj.name, module_name)]

        # setting __package__ in python 2 is weird.  __package__ is
        # set on a module *only* if that module *itself* imports
        # something.  legally this is because that's what pep 0366
        # says; practically it's because __package__ is only set in
        # get_parent in import.c.  we mimic that behavior here by
        # reaching into sys.modules to retrieve our parent package.
        # that's something we can do because'
        #
        # https://www.python.org/dev/peps/pep-0366/
        # http://thread.gmane.org/gmane.comp.python.devel/113438

        if package:
            sys.modules[package].__package__ = package

        self._populate_module(module, fullname, module_name)

        return module


class PyOpenatLoader(OpenatLoader):

    def _populate_module(self, module, fullname, shortname):
        sys.modules[fullname] = module
        try:
            with self.dirobj.open(self.path) as f:
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
        uncompiled = self.path.replace('.pyc', '.py')
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
            with self.dirobj.open(self.path) as f:
                self.fileobj = f
                magic = self._read_marshal_long(f)
                if magic is None or magic != self.MAGIC:
                    raise LoadCompiledModuleFailure(
                        ImportError('Bad magic number in '
                                    '{}'.format(self.path)))
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
        self.pyc_loader.path = self.py_loader.path.replace('.py', '.pyc')

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
            with self.dirobj.open(self.path) as so:
                so_fd = so.fileno()
                loaded_so = fdlopen(so_fd, RTLD_NOW)
                initmodule_pointer = dlsym(loaded_so, 'init%s' % shortname)
                initmodule = callable_with_gil(initmodule_pointer)

                # initmodule apparently unsets __file__, but leaves
                # other attributes alone
                __file__ = module.__file__

                with _Py_PackageContext(fullname, shortname):
                    initmodule()
                m = sys.modules[fullname]

                m.__file__ = __file__
                return m
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            raise ImportError(e)
        finally:
            gc.enable()


class OpenatFileFinder(BaseOpenatFileFinder):

    def __call__(self, path):
        if self.path != path:
            raise ImportError

    def _find_loader(self, dirobj, fullname):
        components = fullname.split('.')

        if imp.is_builtin(fullname):
            return None

        for suffix, mode, kind in MODULE_TYPE_TUPLES:
            base_path = os.path.join(self.path, *components)

            maybe_package = os.path.join(base_path, '__init__') + suffix
            maybe_module = base_path + suffix

            if dirobj.exists(maybe_package):
                path = maybe_package
            elif dirobj.exists(maybe_module):
                path = maybe_module
            else:
                continue

            if kind == imp.C_EXTENSION:
                loader = RTLDOpenatLoader
            elif kind == imp.PY_SOURCE:
                loader = TryPycThenPyOpenatLoader
            elif kind == imp.PY_COMPILED:
                loader = PyCompiledOpenatLoader
            return loader(fullname, path, dirobj)

    def find_module(self, fullname, path=None):
        for dirobj in self.dirobjs_from_path(path):
            loader = self._find_loader(dirobj, fullname)
            if loader:
                return loader

    def __repr__(self):
        return '<{} for {}">'.format(self.__class__.__name__, self.path)

# cribbed from fsnix's source and http://pymotw.com/2/sys/imports.html
import gc
import errno
import imp
import os
from fsnix import fs, util
import sys
import struct
import ctypes
import cffi
import marshal


ffi = cffi.FFI()

ffi.cdef('''
static const int RTLD_NOW;
static const int RTLD_LAZY;

void *
fdlopen(int fd, int mode);

void *
dlsym(void * restrict handle, const char * restrict symbol);

char *
dlerror(void);

uintptr_t
addrof(void * f);

''')
lib = ffi.verify('''
#include <dlfcn.h>


uintptr_t
addrof(void * p){
    return (uintptr_t)p;
}
''')


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
            return sys.modules[fullname]
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
                loaded_so = lib.fdlopen(so_fd, lib.RTLD_NOW)
                if loaded_so == ffi.NULL:
                    raise RuntimeError(ffi.string(lib.dlerror()))

                initmodule_pointer = lib.dlsym(loaded_so, 'init%s' % shortname)
                if initmodule_pointer == ffi.NULL:
                    raise RuntimeError(ffi.string(lib.dlerror()))

                addr = lib.addrof(initmodule_pointer)
                initmodule = ctypes.PYFUNCTYPE(None)(addr)
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

    def find_module(self, fullname, path=None):
        if path:
            if not path.startswith(self.path_entry):
                return None
            path = path.replace(self.path_entry, '')
            if path.startswith('/'):
                path = path[1:]

            dirobj = fopendirat(self.directory.fileno(), path)
        else:
            dirobj = self.directory

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


def install(rights, preimports=('random',)):
    for preimport in preimports:
        __import__(preimport)

    for entry in sys.path:
        if os.path.isdir(entry):
            sys.meta_path.append(OpenatFinder(entry, rights))


def test():
    from spyce import (Rights, CAP_READ, CAP_LOOKUP, CAP_SEEK,
                       CAP_MMAP, CAP_FCNTL, CAP_FSTAT, CAP_MMAP_RX,
                       enterCapabilityMode)

    rights = Rights([CAP_READ, CAP_LOOKUP, CAP_FSTAT, CAP_SEEK,
                     CAP_MMAP_RX, CAP_MMAP, CAP_FCNTL])

    install(rights)
    enterCapabilityMode()

    import mmap
    import urllib2


if __name__ == '__main__':
    test()

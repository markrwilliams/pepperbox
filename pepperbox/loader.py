import gc
import _imp
from importlib.util import spec_from_file_location
from importlib.abc import SourceLoader, MetaPathFinder
from importlib.machinery import (ModuleSpec,
                                 ExtensionFileLoader,
                                 SOURCE_SUFFIXES, BYTECODE_SUFFIXES,
                                 BuiltinImporter)
import os
import sys
from pepperbox._ffi import fdlopen, RTLD_NOW, dlsym, callable_with_gil
from pepperbox.support import opendir


class OpenatLoader(object):
    def __init__(self, fullname, path, dirobj):
        self.fullname = fullname
        self.path = path
        self.dirobj = dirobj


class OpenatSourceFileLoader(OpenatLoader, SourceLoader):

    def path_stats(self, path):
        stats = self.dirobj.lstat(path)
        return {'mtime': stats.st_mtime, 'size': stats.st_size}

    def get_data(self, path):
        with self.dirobj.open(path, 'rb') as f:
            return f.read()

    def get_filename(self, path):
        return self.path


class OpenatSourcelessFileLoader(OpenatSourceFileLoader):

    def get_source(self, fullname):
        return None


class OpenatExtensionFileLoader(OpenatLoader, ExtensionFileLoader):

    def create_module(self, spec):
        _, _, shortname = spec.name.rpartition('.')
        shortname = shortname.encode('ascii')
        gc.disable()
        try:
            with self.dirobj.open(self.path) as so:
                so_fd = so.fileno()
                loaded_so = fdlopen(so_fd, RTLD_NOW)
                initmodule_pointer = dlsym(loaded_so, b'PyInit_' + shortname)
                initmodule = callable_with_gil(initmodule_pointer)
                m = initmodule()
                m.__file__ = self.path
                return m
        finally:
            gc.enable()

    def exec_module(self, module):
        return module


class OpenatFileFinder(MetaPathFinder):

    def __init__(self, path, rights=()):
        self.path = path
        self.dirobj = opendir(path)
        for rightsObj in rights:
            rightsObj.limitFile(self.dirobj)

        loaders = [(OpenatExtensionFileLoader, _imp.extension_suffixes()),
                   (OpenatSourceFileLoader, SOURCE_SUFFIXES),
                   (OpenatSourcelessFileLoader, BYTECODE_SUFFIXES)]
        self._loaders = [(suffix, loader)
                         for loader, suffixes in loaders
                         for suffix in suffixes]

    def find_spec(self, fullname, path=None, target=None):
        """Try to find a loader for the specified module, or the namespace
        package portions. Returns (loader, list-of-portions)."""
        builtin_spec = BuiltinImporter.find_spec(fullname, path, target)
        if builtin_spec:
            return builtin_spec
        is_namespace = False
        tail_module = fullname.rpartition('.')[2]

        if path:
            dirobjs = []
            for p in path:
                try:
                    dirobj = self.dirobj.opendir(p)
                except ValueError:
                    return
                dirobjs.append(dirobj)
        else:
            dirobjs = [self.dirobj]

        # Check if the module is the name of a directory (and thus a package).
        for dirobj in dirobjs:
            if dirobj.isdir(tail_module):
                base_path = os.path.join(self.path, tail_module)
                for suffix, loader_class in self._loaders:
                    init_filename = '__init__' + suffix
                    full_path = os.path.join(base_path, init_filename)
                    if dirobj.isfile(full_path):
                        _loader = loader_class(fullname, full_path,
                                               dirobj)
                        return spec_from_file_location(
                            fullname, full_path,
                            loader=_loader,
                            submodule_search_locations=[base_path])
                else:
                    # If a namespace package, return the path if we don't
                    #  find a module in the next section.
                    is_namespace = dirobj.isdir(tail_module)
            # Check for a file w/ a proper suffix exists.
            for suffix, loader_class in self._loaders:
                fn = tail_module + suffix
                full_path = os.path.join(dirobj.name, fn)
                if dirobj.isfile(fn):
                    _loader = loader_class(fullname, full_path, dirobj)
                    return spec_from_file_location(
                        fullname, full_path,
                        loader=_loader,
                        submodule_search_locations=None)

            if is_namespace:
                spec = ModuleSpec(fullname, None)
                spec.submodule_search_locations = [base_path]
                return spec
        return None


def install(rights, preimports=()):
    for preimport in preimports:
        __import__(preimport)

    meta_path = [OpenatFileFinder(entry, rights)
                 for entry in sys.path
                 if os.path.isdir(entry)]
    sys.meta_path = meta_path

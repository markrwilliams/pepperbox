import imp
import sys

import pytest

IS_PYTHON_27 = sys.version_info.major == 2 and sys.version_info.minor == 7
IS_PYTHON_34 = sys.version_info.major == 3 and sys.version_info.minor == 4

only_py27 = pytest.mark.skipif(not IS_PYTHON_27, reason='only for Python 2.7')
only_py34 = pytest.mark.skipif(not IS_PYTHON_34, reason='only for Python 3.4')


class LoadModuleOrPackage(object):
    '''A context manager that loads a package or module.

    The module and any intermediate packages are available in
    sys.modules inside the with block.  They are removed after it terminates.

    :param directory: Path to the directory that contains the
                      requested module/package path.
    :param module_or_package_path: A dotted import path
    '''

    def __init__(self, directory, module_or_package_path):
        self.directory = directory
        self.module_or_package_path = module_or_package_path
        self.to_uncache = []

    def __enter__(self):
        fqn = self.module_or_package_path.split('.')
        path = [self.directory]
        for i, shortname in enumerate(fqn, 1):
            # This function does not handle hierarchical module names
            # (names containing dots). In order to find P.M, that is,
            # submodule M of package P, use find_module() and
            # load_module() to find and load package P, and then use
            # find_module() with the path argument set to
            # P.__path__. When P itself has a dotted name, apply this
            # recipe recursively.
            # https://docs.python.org/2/library/imp.html#imp.find_module
            name = '.'.join(fqn[:i])
            spec = imp.find_module(shortname, path)
            module_or_package = imp.load_module(name, *spec)

            path = getattr(module_or_package, '__path__', [])
            self.to_uncache.append(name)
        return module_or_package

    def __exit__(self, *exc_info):
        for name in self.to_uncache:
            sys.modules.pop(name, None)


def mod__files__equal(loaded, actual):
    assert loaded.__file__ == actual.__file__

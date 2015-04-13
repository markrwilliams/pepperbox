from collections import namedtuple
import pytest
import py
import os
from pepperbox.support import DirectoryFD
from .common import (only_py27, IS_PYTHON_27,
                     mod__files__equal,
                     LoadModuleOrPackage)

pytestmark = only_py27


def walk_up_directory_tree(loader, fixture, is_package=False):
    # attempt to load a given module at all possible directory depths.
    #
    # so for a module /home/you/a/b/c/d.py
    #
    # directory = /home/you/a/b/c, relpath = d.py
    # directory = /home/you/a/b, relpath = c/d.py
    # ...
    # directory = /, relpath = home/you/a/b/c/d.py
    #
    # this ensures that __name__ and __file__ are determined correctly
    # regardless of a module's location
    name = fixture.module.__name__
    head = str(fixture.path)
    args = ()

    while head and head != os.path.sep:
        head, new_tail = os.path.split(head)

        args = (new_tail,) + args
        tail = os.path.join(*args)

        dirobj = DirectoryFD(head)
        pol = loader(dirobj, tail, is_package)
        if fixture.package:
            # because of the particulars of setting module.__package__,
            # we need to make sure the immediate parents of this
            # module or package are available in sys.modules
            package_parent = fixture.path.pypkgpath().dirname
            with LoadModuleOrPackage(package_parent,
                                     fixture.package):
                module = pol.load_module(name)
        else:
            module = pol.load_module(name)
        yield module


def mod__files__expected(loaded, actual):
    loaded_p = py.path.local(loaded.__file__)
    actual_p = py.path.local(actual.__file__)
    assert loaded_p.dirname == actual_p.dirname
    assert loaded_p.purebasename == actual_p.purebasename


def _parametrize():
    from pepperbox.py27 import loader

    return pytest.mark.parametrize(
        'category,loader,compare_file_attrs',
        [('py_and_pyc', loader.PyOpenatLoader, mod__files__expected),
         ('no_py', loader.PyCompiledOpenatLoader, mod__files__equal),
         ('py_and_pyc', loader.TryPycThenPyOpenatLoader,
          mod__files__expected),
         ('extension_module', loader.RTLDOpenatLoader, mod__files__expected)])


parametrized_loaders = pytest.mark.parametrize_skipif(
    _parametrize,
    skipif=not IS_PYTHON_27)


@parametrized_loaders
def test_loaders_succeed_with_modules(modules_by_category,
                                      category,
                                      loader, compare_file_attrs):
    for fixture in modules_by_category.get(category, ()):
        for loaded_module in walk_up_directory_tree(loader, fixture,
                                                    is_package=False):

            assert loaded_module.contents == fixture.module.contents
            assert loaded_module.__name__ == fixture.module.__name__
            assert loaded_module.__package__ == fixture.module.__package__

            compare_file_attrs(loaded_module, fixture.module)

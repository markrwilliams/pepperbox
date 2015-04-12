import pytest
import py
import os
from pepperbox.support import DirectoryFD
from .common import (only_py27, IS_PYTHON_27,
                     mod__files__equal)

pytestmark = only_py27


def walk_up_directory_tree(loader, path, name, is_package=False):
    head = str(path)
    args = ()
    while head and head != os.path.sep:
        head, new_tail = os.path.split(head)

        args = (new_tail,) + args
        tail = os.path.join(*args)

        dirobj = DirectoryFD(head)
        pol = loader(dirobj, tail, is_package)
        yield pol.load_module(name)


def mod__files__expected(loaded, actual):
    loaded_p = py.path.local(loaded.__file__)
    actual_p = py.path.local(actual.__file__)
    assert loaded_p.dirname == actual_p.dirname
    assert loaded_p.purebasename == actual_p.purebasename


def noop(*args, **kwargs):
    pass


def _parametrize():
    from pepperbox.py27 import loader

    return pytest.mark.parametrize(
        'category,loader,compare_file_attrs',
        [('py_and_pyc', loader.PyOpenatLoader, mod__files__expected),
         ('no_py', loader.PyCompiledOpenatLoader, mod__files__equal),
         ('py_and_pyc', loader.TryPycThenPyOpenatLoader,
          mod__files__expected),
         ('extension_module', loader.RTLDOpenatLoader, noop)])


parametrized_loaders = pytest.mark.parametrize_skipif(
    _parametrize,
    skipif=not IS_PYTHON_27)


@parametrized_loaders
def test_loaders_succeed_with_modules(modules_by_category,
                                      category,
                                      loader, compare_file_attrs):
    for fixture in modules_by_category.get(category, ()):
        fullname = fixture.module.__name__
        is_package = bool(fixture.module.__package__)
        for loaded_module in walk_up_directory_tree(loader,
                                                    fixture.path,
                                                    fullname,
                                                    is_package):

            assert loaded_module.contents == fixture.module.contents
            assert loaded_module.__name__ == fixture.module.__name__
            if is_package:
                assert loaded_module.__package__ == fixture.module.__package__
                assert loaded_module.__path__ == fixture.module.__path__

            compare_file_attrs(loaded_module, fixture.module)

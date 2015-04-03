import pytest
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


def mod__files__py_to_pyc(loaded, actual):
    loaded_no_ext, loaded_ext = os.path.splitext(loaded.__file__)
    actual_no_ext, actual_ext = os.path.splitext(actual.__file__)
    assert loaded_no_ext == actual_no_ext
    assert loaded_ext == '.pyc'


def _parametrize():
    from pepperbox.py27 import loader

    return pytest.mark.parametrize(
        'category,loader,compare_file_attrs',
        [('py_and_pyc', loader.PyOpenatLoader, mod__files__equal),
         ('no_py', loader.PyCompiledOpenatLoader, mod__files__equal),
         ('py_and_pyc', loader.TryPycThenPyOpenatLoader,
          mod__files__py_to_pyc)])


parametrized_loaders = pytest.mark.parametrize_skipif(
    _parametrize,
    skipif=not IS_PYTHON_27)


@parametrized_loaders
def test_loaders_succeed_with_modules(package_directory_tree,
                                      category,
                                      loader, compare_file_attrs):
    modules = package_directory_tree.modules_by_category.get(category, ())

    for name in modules:
        path, module = package_directory_tree.modules[name]
        shortname = package_directory_tree.shortname(name)
        for loaded_module in walk_up_directory_tree(loader,
                                                    path,
                                                    shortname,
                                                    is_package=False):
            assert loaded_module.contents == module.contents
            compare_file_attrs(loaded_module, module)


@parametrized_loaders
def test_loaders_succeed_with_packages(package_directory_tree,
                                       category,
                                       loader, compare_file_attrs):
    packages = package_directory_tree.packages_by_category.get(category, ())

    for name in packages:
        path, module = package_directory_tree.packages[name]
        name = '__init__'
        for loaded_module in walk_up_directory_tree(loader,
                                                    path,
                                                    name,
                                                    is_package=True):
            compare_file_attrs(loaded_module, module)


@parametrized_loaders
def test_loaders_inaccessible_module_fails(tmpdir,
                                           category,
                                           loader,
                                           compare_file_attrs):
    with pytest.raises(ImportError):
        missing_pol = loader(DirectoryFD(str(tmpdir)),
                             'missing.py',
                             is_package=False)
        missing_pol.load_module('missing')

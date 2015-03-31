import pytest
from pepperbox.support import DirectoryFD
from .common import (only_py34, IS_PYTHON_34,
                     mod__files__equal)

pytestmark = only_py34


def _parametrize():
    from pepperbox.py34 import loader

    return pytest.mark.parametrize(
        'category,loader,compare_file_attrs',
        [('py_and_pyc', loader.OpenatSourceFileLoader, mod__files__equal),
         ('no_py', loader.OpenatSourcelessFileLoader, mod__files__equal)])


parametrized_loaders = pytest.mark.parametrize_skipif(
    _parametrize,
    skipif=not IS_PYTHON_34)


@parametrized_loaders
def test_loaders_succeed_with_modules(package_directory_tree,
                                      category,
                                      loader, compare_file_attrs):
    modules = package_directory_tree.modules_by_category.get(category, ())

    for name in modules:
        path, module = package_directory_tree.modules[name]
        loader_inst = loader(name, str(path),
                             DirectoryFD(str(path.join('..'))))
        loaded_module = loader_inst.load_module(name)
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
        loader_inst = loader(name, str(path),
                             DirectoryFD(str(path.join('..'))))
        loaded_module = loader_inst.load_module(name)
        compare_file_attrs(loaded_module, module)


@parametrized_loaders
def test_loaders_inaccessible_module_fails(tmpdir,
                                           category,
                                           loader,
                                           compare_file_attrs):
    with pytest.raises(FileNotFoundError):
        loader_inst = loader('missing',
                             str(tmpdir.join('missing.py')),
                             DirectoryFD(str(tmpdir)))
        loader_inst.load_module('missing')

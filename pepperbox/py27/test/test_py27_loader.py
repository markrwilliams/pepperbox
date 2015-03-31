import operator
import pytest
import sys
import os
from pepperbox.support import DirectoryFD

IS_PYTHON_3 = sys.version_info.major > 2

pytestmark = pytest.mark.skipif(IS_PYTHON_3, reason='only for Python 2.7')


def pytest_generate_tests(metafunc):
    if IS_PYTHON_3:
        return

    from pepperbox.py27 import loader

    def files_equal(loaded, actual):
        assert loaded.__file__ == actual.__file__

    def py_to_pyc(loaded, actual):
        loaded_no_ext, loaded_ext = os.path.splitext(loaded.__file__)
        actual_no_ext, actual_ext = os.path.splitext(actual.__file__)
        assert loaded_no_ext == actual_no_ext
        assert loaded_ext == '.pyc'

    categories_loaders = [
        ('no_pyc', loader.PyOpenatLoader, files_equal),
        ('no_py', loader.PyCompiledOpenatLoader, files_equal),
        ('no_pyc', loader.TryPycThenPyOpenatLoader, py_to_pyc)]

    idlist = [category for category, _, _ in categories_loaders]
    argnames = ('category', 'loader', 'compare_file_attrs')
    argvalues = categories_loaders

    metafunc.parametrize(argnames, argvalues, ids=idlist, scope='function')


def test_loaders_succeed_with_modules(package_directory_tree,
                                      category,
                                      loader, compare_file_attrs):
        for name in package_directory_tree.modules_by_category[category]:
            path, module = package_directory_tree.modules[name]
            shortname = package_directory_tree.shortname(name)
            head = str(path)
            args = ()
            while head and head != os.path.sep:
                head, new_tail = os.path.split(head)

                args = (new_tail,) + args
                tail = os.path.join(*args)

                dirobj = DirectoryFD(head)
                pol = loader(head, dirobj, tail, is_package=False)
                loaded_module = pol.load_module(shortname)
                assert loaded_module.contents == module.contents
                compare_file_attrs(loaded_module, module)


def test_PyOpenatLoader_inaccessible_module_fails(tmpdir,
                                                  category,
                                                  loader,
                                                  compare_file_attrs):
    with pytest.raises(ImportError):
        missing_pol = loader(str(tmpdir),
                             DirectoryFD(str(tmpdir)),
                             'missing.py',
                             is_package=False)
        missing_pol.load_module('missing')

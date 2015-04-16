import pytest
import os
from pepperbox.support import DirectoryFD
from .common import (only_py27,
                     CATEGORIES, CATEGORIES_TABLE, LOADER, in_category,
                     track_tests, reset_tests,
                     TestsForPyLoader,
                     TestsForPyCompiledLoader,
                     TestsForExtensionModule,
                     TestsForPycWithBadMagicNumber,
                     LoadModuleOrPackage)

pytestmark = only_py27


def setup_module(module):
    track = track_tests(module)

    from pepperbox.py27 import loader as L

    @in_category('package')
    @in_category('py_and_pyc')
    class TestsForTryPycThenPyLoader(TestsForPyCompiledLoader):
        pass

    track(TestsForPyLoader).loader = L.PyOpenatLoader
    track(TestsForPyCompiledLoader).loader = L.PyCompiledOpenatLoader
    track(TestsForTryPycThenPyLoader).loader = L.TryPycThenPyOpenatLoader
    track(TestsForExtensionModule).loader = L.RTLDOpenatLoader
    track(TestsForPyCompiledLoader).loader = L.PyCompiledOpenatLoader
    track(TestsForPycWithBadMagicNumber).loader = L.PyCompiledOpenatLoader

teardown_module = reset_tests


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
                                     str(fixture.path),
                                     fixture.package):
                module = pol.load_module(name)
        else:
            module = pol.load_module(name)
        yield module


def _load_modules_in_category(modules_by_category, category):
    for fixture in modules_by_category.get(category, ()):
        for tests_for_loader in CATEGORIES_TABLE[category][LOADER]:
            is_package = category == 'package'
            tests = tests_for_loader(is_empty=is_package)
            yield tests, fixture, walk_up_directory_tree(tests.loader,
                                                         fixture,
                                                         is_package=is_package)


@pytest.mark.parametrize('category', CATEGORIES - set(['bad_pyc']))
def test_loaders_succeed(modules_by_category, category):
    for tests, fixture, modules_iter in _load_modules_in_category(
            modules_by_category, category):
        for module in modules_iter:
            tests.assert_modules_equal(module, fixture.module)


def test_bad_pycs_fail(modules_by_category):
    for tests, fixture, modules_iter in _load_modules_in_category(
            modules_by_category, 'bad_pyc'):
        while True:
            try:
                with tests.assert_import_fails():
                    next(modules_iter)
            except StopIteration:
                break

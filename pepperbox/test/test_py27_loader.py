import pytest
import os
from pepperbox.support import DirectoryFD
from .common import (only_py27,
                     track_tests, reset_tests,
                     TestsForPyLoader,
                     TestsForPyCompiledLoader,
                     TestsForTryPycThenPyLoader,
                     TestsForExtensionModule,
                     TestsForPycWithBadMagicNumber,
                     LoadModuleOrPackage)

pytestmark = only_py27


def setup_module(module):
    track = track_tests(module)

    from pepperbox.py27 import loader as L

    track(TestsForPyLoader).loader = L.PyOpenatLoader
    track(TestsForPyCompiledLoader).loader = L.PyCompiledOpenatLoader
    track(TestsForTryPycThenPyLoader).loader = L.TryPycThenPyOpenatLoader
    track(TestsForExtensionModule).loader = L.RTLDOpenatLoader
    track(TestsForPyCompiledLoader).loader = L.PyCompiledOpenatLoader
    track(TestsForPycWithBadMagicNumber).loader = L.PyCompiledOpenatLoader

teardown_module = reset_tests


def walk_up_directory_tree(fixture):
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
    head = str(fixture.path)
    args = ()

    while head and head != os.path.sep:
        head, new_tail = os.path.split(head)

        args = (new_tail,) + args
        tail = os.path.join(*args)

        dirobj = DirectoryFD(head)
        yield dirobj, tail


def _load_module(loader, fixture):
    name = fixture.module.__name__
    if fixture.package:
        # because of the particulars of setting module.__package__,
        # we need to make sure the immediate parents of this
        # module or package are available in sys.modules
        package_parent = fixture.path.pypkgpath().dirname
        with LoadModuleOrPackage(package_parent,
                                 str(fixture.path),
                                 fixture.package):
            return loader.load_module(name)
    return loader.load_module(name)


@pytest.mark.parametrize('category, setup_fixture, loader_tests',
                         pytest.pepperbox_loader_table)
def test_loaders(category, setup_fixture, loader_tests):
    fixture = setup_fixture()
    is_package = category == 'package'
    tests = loader_tests(is_empty=is_package)
    for dirobj, tail in walk_up_directory_tree(fixture):
        this_loader = tests.loader(dirobj, tail, is_package)
        if tests.should_fail:
            with tests.assert_import_fails():
                _load_module(this_loader, fixture)
        else:
            module = _load_module(this_loader, fixture)
            tests.assert_modules_equal(module, fixture.module)

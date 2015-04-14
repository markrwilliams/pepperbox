import itertools
import pytest
import os
from pepperbox.support import DirectoryFD
from .common import (only_py27,
                     CATEGORIES, CATEGORIES_TABLE, LOADER,
                     TestsForPyLoader,
                     TestsForPyCompiledLoader,
                     TestsForTryPycThenPyLoader,
                     TestsForExtensionModule,
                     LoadModuleOrPackage)

pytestmark = only_py27

PY27_LOADER = 'pepperbox.py27.loader'
TestsForPyLoader.set_loader(PY27_LOADER, 'PyOpenatLoader')
TestsForPyCompiledLoader.set_loader(PY27_LOADER, 'PyCompiledOpenatLoader')
TestsForTryPycThenPyLoader.set_loader(PY27_LOADER, 'TryPycThenPyOpenatLoader')
TestsForExtensionModule.set_loader(PY27_LOADER, 'RTLDOpenatLoader')


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


@pytest.mark.parametrize('category', CATEGORIES)
def test_loaders_succeed(modules_by_category, category):
    for fixture in modules_by_category.get(category, ()):
        for tests_for_loader in CATEGORIES_TABLE[category][LOADER]:
            is_package = category == 'package'
            tests = tests_for_loader(is_empty=is_package)
            for loaded_module in walk_up_directory_tree(tests.loader,
                                                        fixture,
                                                        is_package=is_package):
                tests.assert_modules_equal(loaded_module, fixture.module)

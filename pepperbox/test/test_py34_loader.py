import pytest
from pepperbox.support import DirectoryFD
from .common import (only_py34,
                     CATEGORIES, CATEGORIES_TABLE, LOADER,
                     track_tests, reset_tests,
                     TestsForPyLoader,
                     TestsForPyCompiledLoader,
                     TestsForExtensionModule,
                     LoadModuleOrPackage)

pytestmark = only_py34


def setup_module(module):
    track = track_tests(module)

    from pepperbox.py34 import loader as L

    track(TestsForPyLoader).loader = L.OpenatSourceFileLoader
    track(TestsForPyCompiledLoader).loader = L.OpenatSourcelessFileLoader
    track(TestsForExtensionModule).loader = L.OpenatExtensionFileLoader


teardown_module = reset_tests


@pytest.mark.parametrize('category', CATEGORIES - set(['extension_module']))
def test_loaders_succeed(modules_by_category, category):
    is_package = category == 'package'

    for fixture in modules_by_category.get(category, ()):
        for tests_for_loader in CATEGORIES_TABLE[category][LOADER]:
            name = fixture.module.__name__
            path = fixture.path
            parent = str(path.pypkgpath() or path.join('..'))
            tests = tests_for_loader(is_empty=is_package)

            loader = tests.loader(name,
                                  str(path),
                                  DirectoryFD(parent))

            loaded_module = loader.load_module(name)
            tests.assert_modules_equal(loaded_module, fixture.module)

import pytest
from pepperbox.support import DirectoryFD
from .common import (only_py34,
                     track_tests, reset_tests,
                     TestsForPyLoader,
                     TestsForPyCompiledLoader,
                     TestsForExtensionModule)

pytestmark = only_py34


def setup_module(module):
    track = track_tests(module)

    from pepperbox.py34 import loader as L

    track(TestsForPyLoader).loader = L.OpenatSourceFileLoader
    track(TestsForPyCompiledLoader).loader = L.OpenatSourcelessFileLoader
    track(TestsForExtensionModule).loader = L.OpenatExtensionFileLoader


teardown_module = reset_tests


@pytest.mark.parametrize('category, setup_fixture, loader_tests',
                         pytest.pepperbox_loader_table)
def test_loaders(category, setup_fixture, loader_tests):
    fixture = setup_fixture()

    is_package = category == 'package'
    name = fixture.module.__name__
    path = fixture.path
    parent = str(path.pypkgpath() or path.join('..'))
    tests = loader_tests(is_empty=is_package)

    loader = tests.loader(name,
                          str(path),
                          DirectoryFD(parent))

    loaded_module = loader.load_module(name)

    tests.assert_modules_equal(loaded_module, fixture.module)

    if category == 'extension_module':
        # TODO: this doesn't test what it appears to because the two
        # modules inevitably share the same backing .so.  python never
        # calls dlclose on sos it's dlopened, so to properly test
        # per-module state, it's likely necessary that the fixture
        # module not be loaded prior to the test!
        loaded_module.test_state() == fixture.module.test_state()

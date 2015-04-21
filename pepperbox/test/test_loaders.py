import os
import pytest

from ._test_loaders_support import LoadModuleOrPackage

from ..support import DirectoryFD
from .common import only_py27, only_py34


@only_py27
class TestsPy27Loader(object):

    def walk_up_directory_tree(self, fixture):
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

    def _load_module(self, loader, fixture):
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
    def test_loaders(self, category, setup_fixture, loader_tests):
        fixture = setup_fixture()
        is_package = category == 'package'
        tests = loader_tests(is_empty=is_package)
        for dirobj, tail in self.walk_up_directory_tree(fixture):
            this_loader = tests.loader_cls(dirobj, tail, is_package)
            if tests.raises:
                with pytest.raises(*tests.raises):
                    self._load_module(this_loader, fixture)
            else:
                module = self._load_module(this_loader, fixture)
                tests.assert_modules_equal(module, fixture.module)


@only_py34
@pytest.mark.parametrize('category, setup_fixture, loader_tests',
                         pytest.pepperbox_loader_table)
def test_py34_loaders(category, setup_fixture, loader_tests):
    fixture = setup_fixture()

    is_package = category == 'package'
    name = fixture.module.__name__
    path = fixture.path
    parent = str(path.pypkgpath() or path.join('..'))
    tests = loader_tests(is_empty=is_package)

    loader = tests.loader_cls(name,
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

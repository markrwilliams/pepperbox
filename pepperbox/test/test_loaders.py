import pytest
import os
import importlib
import subprocess
import sys
from collections import namedtuple
import imp
import py.path
import py_compile

from ..support import PY_TAG, DirectoryFD
from .common import IS_PYTHON_27, only_py27, only_py34

FIXTURE_SETUPS = {}

CATEGORIES = frozenset(['package',
                        'py_and_pyc',
                        'no_py',
                        'extension_module',
                        'bad_pyc'])


def fixture_for(category):
    assert category in CATEGORIES

    def wrapper(cls):
        FIXTURE_SETUPS[category] = cls
        return cls

    return wrapper

LOADER_TESTS = {}


def loader_tests_for(*categories):
    assert not (set(categories) - CATEGORIES)

    def wrapper(cls):
        for category in categories:
            LOADER_TESTS.setdefault(category, []).append(cls)
        return cls

    return wrapper


def all_lineages(deepest_lineage):
    generations = deepest_lineage.split('.')
    return [tuple(generations[:i]) for i in range(len(generations) + 1)]


def _skipif_istrue(mark):
    return mark.name == 'skipif' and mark.args[0]


def _check_class_skipifs(cls):
    return any(_skipif_istrue(m) for m in getattr(cls, 'pytestmark', ()))


def category_fixture_loaders(root, directory, lineage):
    if not lineage:
        # top level fixtures
        relevant_categories = CATEGORIES - set(['package'])
    else:
        relevant_categories = CATEGORIES

    category_fixture_loaders = []
    for category in relevant_categories:
        for loader_tests in LOADER_TESTS[category]:
            fixture_setup_cls = FIXTURE_SETUPS[category]

            if (_check_class_skipifs(loader_tests) or
               _check_class_skipifs(fixture_setup_cls)):
                continue

            fixture_setup = fixture_setup_cls(root, directory, lineage)
            category_fixture_loaders.append(
                (category, fixture_setup, loader_tests))
    return category_fixture_loaders


def gen_category_fixture_loaders(fixture_dir, deepest_lineage):
    all_category_fixture_loaders = []
    root = py.path.local(fixture_dir)

    for lineage in all_lineages(deepest_lineage):
        directory = root.join(*lineage)
        all_category_fixture_loaders.extend(category_fixture_loaders(root,
                                                                     directory,
                                                                     lineage))
    return all_category_fixture_loaders


def pytest_generate_tests(metafunc):
    if not hasattr(metafunc.function, 'parametrize_loader_tests'):
        return
    config = metafunc.config
    fixture_dir = py.path.local(config.getoption('fixture_dir'))
    lineage = config.getoption('lineage')
    loader_table = gen_category_fixture_loaders(fixture_dir, lineage)

    metafunc.parametrize('category, setup_fixture, loader_tests',
                         loader_table)


FIXTURES_SOURCE = py.path.local(__file__).dirpath('fixtures_src')


class ModuleFixture(namedtuple('ModuleFixture',
                               'shortname module path')):

    @property
    def package(self):
        return self.module.__name__.rpartition('.')[0]


class _GetAttributeForVersion(object):
    _MISSING = object()

    def _attribute_for_version(self, name):
        attr = getattr(self, '_{}_{}'.format(PY_TAG, name), self._MISSING)
        if attr is self._MISSING:
            raise RuntimeError("Unsupported version {}".format(PY_TAG))
        return attr


class LoadModuleOrPackage(_GetAttributeForVersion):
    '''A context manager that loads a package or module.

    The module and any intermediate packages are available in
    sys.modules inside the with block.  They are removed after it terminates.
    '''

    def __init__(self, root, filepath, module_or_package_path):
        self.root = root
        self.filepath = filepath
        self.module_or_package_path = module_or_package_path
        self.to_uncache = []

    def _cpython_27_import_module(self):
        fqn = self.module_or_package_path.split('.')
        path = [self.root]
        for i, shortname in enumerate(fqn, 1):
            # This function does not handle hierarchical module names
            # (names containing dots). In order to find P.M, that is,
            # submodule M of package P, use find_module() and
            # load_module() to find and load package P, and then use
            # find_module() with the path argument set to
            # P.__path__. When P itself has a dotted name, apply this
            # recipe recursively.
            # https://docs.python.org/2/library/imp.html#imp.find_module
            name = '.'.join(fqn[:i])
            spec = imp.find_module(shortname, path)
            module_or_package = imp.load_module(name, *spec)

            path = getattr(module_or_package, '__path__', [])
            self.to_uncache.append(name)
        return module_or_package

    def _cpython_34_import_module(self):
        from importlib.util import spec_from_file_location
        spec = spec_from_file_location(self.module_or_package_path,
                                       self.filepath)
        module_or_package = spec.loader.load_module()
        self.to_uncache.extend(self.module_or_package_path.split('.'))
        return module_or_package

    def __enter__(self):
        return self._attribute_for_version('import_module')()

    def __exit__(self, *exc_info):
        for name in self.to_uncache:
            sys.modules.pop(name, None)


class SetsUpFixture(object):
    SOURCE = None
    TARGET_FN = None
    module_name = None

    _fixture = None

    def __init__(self, root, directory, lineage):
        self.root = root
        self.directory = directory
        self.lineage = lineage

    def create(self):
        pass

    def ensure(self, directory, is_package=True):
        directory.ensure(dir=True)
        if is_package:
            # TODO: this is not fully testing the __init__ related code
            init = directory.join('__init__.py').ensure()
            py_compile.compile(str(init))

    def path(self, directory):
        return directory.join(self.TARGET_FN)

    def install(self, directory, path):
        pass

    def load(self, directory, filepath, lineage):
        fqn = list(lineage)
        if self.module_name is not None:
            fqn.append(self.module_name)

        module_or_package = '.'.join(fqn)

        with LoadModuleOrPackage(str(directory),
                                 str(filepath),
                                 module_or_package) as mop:
            return mop

    def __call__(self):
        if self._fixture:
            return self._fixture

        self.ensure(self.directory, bool(self.lineage))
        path = self.path(self.directory)
        if not path.exists():
            self.create()
            self.install(self.directory)
        module = self.load(self.root, path, self.lineage)

        if self.module_name is None:
            module_name = self.lineage[-1]
        else:
            module_name = self.module_name

        self._fixture = ModuleFixture(module_name,
                                      module,
                                      path)
        return self._fixture

    def __repr__(self):
        cn = self.__class__.__name__
        return '{}(root={}, directory={}, lineage={})'.format(
            cn, self.root, self.directory, self.lineage)


class TestsForLoaderInCategory(_GetAttributeForVersion):
    raises = ()

    _cpython_27_loader = 'pepperbox.py27.loader'
    _cpython_34_loader = 'pepperbox.py34.loader'

    @property
    def _loader_module(self):
        return importlib.import_module(self._attribute_for_version('loader'))

    @property
    def loader_cls(self):
        return self._attribute_for_version('loader_cls')()

    def __init__(self, is_empty=False):
        self.is_empty = is_empty

    def assert_modules_equal(self, loaded, expected):
        if not self.is_empty:
            assert loaded.contents == expected.contents
        assert loaded.__name__ == expected.__name__
        assert loaded.__package__ == expected.__package__
        self.assert_module_dot_files_equal(loaded, expected)

    def assert_module_dot_files_equal(self, loaded, expected):
        assert loaded.__file__ == expected.__file__


@fixture_for('package')
class PackageFixture(SetsUpFixture):
    TARGET_FN = '__init__.py'


@fixture_for('py_and_pyc')
class SetsUpPyAndPycFixture(SetsUpFixture):
    SOURCE = FIXTURES_SOURCE.join('py_and_pyc.py')
    TARGET_FN = 'py_and_pyc.py'
    module_name = 'py_and_pyc'

    def install(self, location):
        dst = location.join(self.SOURCE.basename)
        self.SOURCE.copy(location)
        py_compile.compile(str(dst))
        return dst


class TestsForPurePythonLoaders(TestsForLoaderInCategory):

    def assert_module_dot_files_equal(self, loaded, expected):
        loaded_p = py.path.local(loaded.__file__)
        actual_p = py.path.local(expected.__file__)
        assert loaded_p.dirname == actual_p.dirname
        assert loaded_p.purebasename == actual_p.purebasename


@loader_tests_for('package', 'py_and_pyc')
class TestsForPyLoader(TestsForPurePythonLoaders):

    def _cpython_27_loader_cls(self):
        return self._loader_module.PyOpenatLoader

    def _cpython_34_loader_cls(self):
        return self._loader_module.OpenatSourceFileLoader

    def assert_module_dot_files_equal(self, loaded, expected):
        super(TestsForPyLoader, self).assert_module_dot_files_equal(loaded,
                                                                    expected)
        assert py.path.local(loaded.__file__).ext == '.py'


@fixture_for('no_py')
class SetsUpNoPyFixture(SetsUpPyAndPycFixture):
    SOURCE = FIXTURES_SOURCE.join('no_py.py')
    TARGET_FN = 'no_py.pyc'
    module_name = 'no_py'

    def _rename_python3_bytecode(self, pure_python):
        # "If the py source file is missing, the pyc file inside
        # __pycache__ will be ignored. This eliminates the problem of
        # accidental stale pyc file imports."
        # https://www.python.org/dev/peps/pep-3147/
        from importlib.util import cache_from_source
        bytecode = py.path.local(cache_from_source(str(pure_python)))
        target_dir, target_fn = pure_python.dirname, pure_python.basename
        target_fn = target_fn.replace('.py', '.pyc')
        target = py.path.local(target_dir).join(target_fn)
        bytecode.copy(target)

    def install(self, location):
        dst = super(SetsUpNoPyFixture, self).install(location)

        if not IS_PYTHON_27:
            self._rename_python3_bytecode(dst)

        dst.remove()


@loader_tests_for('no_py')
class TestsForPyCompiledLoader(TestsForPurePythonLoaders):

    def _cpython_27_loader_cls(self):
        return self._loader_module.PyCompiledOpenatLoader

    def _cpython_34_loader_cls(self):
        return self._loader_module.OpenatSourcelessFileLoader

    def assert_module_dot_files_equal(self, loaded, expected):
        super(TestsForPyCompiledLoader,
              self).assert_module_dot_files_equal(loaded, expected)
        assert py.path.local(loaded.__file__).ext == '.pyc'


@fixture_for('extension_module')
class SetsUpExtensionModule(SetsUpFixture):
    module_name = '{}c'.format(PY_TAG)

    SO_SRC_DIR = FIXTURES_SOURCE.join(PY_TAG)
    SO_BUILD_DIR = 'build'
    TARGET_FN = '{}.so'.format(module_name)
    SOURCE = py.path.local(SO_SRC_DIR).join(SO_BUILD_DIR).join(TARGET_FN)

    def create(self):
        if self.SOURCE.exists():
            return
        subprocess.check_call([sys.executable,
                               'setup.py',
                               'build',
                               '--build-lib',
                               self.SO_BUILD_DIR],
                              cwd=self.SO_SRC_DIR)

    def install(self, location):
        self.SOURCE.copy(location)


@loader_tests_for('extension_module')
class TestsForExtensionModule(TestsForLoaderInCategory):

    def _cpython_27_loader_cls(self):
        return self._loader_module.RTLDOpenatLoader

    def _cpython_34_loader_cls(self):
        return self._loader_module.OpenatExtensionFileLoader

    def assert_module_dot_files_equal(self, loaded, actual):
        pass


@only_py27
@fixture_for('bad_pyc')
class SetsUpPycWithBadMagicNumber(SetsUpNoPyFixture):
    module_name = 'pyc_with_bad_magic_number'
    SOURCE = FIXTURES_SOURCE.join('pyc_with_bad_magic_number.py')
    TARGET_FN = 'pyc_with_bad_magic_number.pyc'

    def path(self, directory):
        path = super(SetsUpPycWithBadMagicNumber, self).path(directory)
        if path.exists():
            path.remove()
        return path

    def load(self, directory, path, lineage):
        mod = super(SetsUpPycWithBadMagicNumber, self).load(directory,
                                                            path,
                                                            lineage)
        path.open('w')
        return mod


@only_py27
@loader_tests_for('package', 'py_and_pyc')
class TestsForTryPycThenPyLoader(TestsForPurePythonLoaders):

    def _cpython_27_loader_cls(self):
        return self._loader_module.TryPycThenPyOpenatLoader


@only_py27
@loader_tests_for('bad_pyc')
class TestsForPycWithBadMagicNumber(TestsForPyCompiledLoader):
    raises = (ImportError,)


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

    @pytest.mark.parametrize_loader_tests
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
@pytest.mark.parametrize_loader_tests
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

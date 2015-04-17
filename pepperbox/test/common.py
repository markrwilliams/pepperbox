import contextlib
import os
import subprocess
import sys
from collections import namedtuple
import imp
import py
import py_compile
import pytest


IS_PYTHON_27 = sys.version_info.major == 2 and sys.version_info.minor == 7
IS_PYTHON_34 = sys.version_info.major == 3 and sys.version_info.minor == 4

only_py27 = pytest.mark.skipif(not IS_PYTHON_27, reason='only for Python 2.7')
only_py34 = pytest.mark.skipif(not IS_PYTHON_34, reason='only for Python 3.4')


def generate_py_tag():
    """like sys.implementation.cache_tag, except:

    1) it's in Python 2

    2) it's a valid Python identifier, so it can be used in module names

    https://www.python.org/dev/peps/pep-0421/#required-attributes
    """

    if hasattr(sys, 'implementation'):
        name = sys.implementation.name
    elif hasattr(sys, 'subversion'):
        name, _, _ = sys.subversion
    else:
        raise RuntimeError("Could not discover interpreter name")

    name = name.lower()
    version = '{}{}'.format(*sys.version_info[:2])

    return '{}_{}'.format(name, version)


PY_TAG = generate_py_tag()

FIXTURES_SOURCE = py.path.local(__file__).dirpath('fixtures_src')


class ModuleFixture(namedtuple('ModuleFixture',
                               'shortname category module path')):

    @property
    def package(self):
        return self.module.__name__.rpartition('.')[0]


class LoadModuleOrPackage(object):
    '''A context manager that loads a package or module.

    The module and any intermediate packages are available in
    sys.modules inside the with block.  They are removed after it terminates.
    '''

    def __init__(self, root, filepath, module_or_package_path):
        self.root = root
        self.filepath = filepath
        self.module_or_package_path = module_or_package_path
        self.to_uncache = []

    if IS_PYTHON_27:
        def _import_module(self):
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
    elif IS_PYTHON_34:
        def _import_module(self):
            from importlib.util import spec_from_file_location
            spec = spec_from_file_location(self.module_or_package_path,
                                           self.filepath)
            module_or_package = spec.loader.load_module()
            self.to_uncache.extend(self.module_or_package_path.split('.'))
            return module_or_package

    def __enter__(self):
        return self._import_module()

    def __exit__(self, *exc_info):
        for name in self.to_uncache:
            sys.modules.pop(name, None)

FIXTURE = 'FIXTURE'
LOADER_TESTS = 'LOADER_TESTS'

CATEGORIES = frozenset(['package',
                        'py_and_pyc',
                        'no_py',
                        'extension_module',
                        'bad_pyc'])

CATEGORIES_TABLE = {k: {FIXTURE: None,
                        LOADER_TESTS: []}
                    for k in CATEGORIES}


def in_category(name, **kwargs):
    assert name in CATEGORIES

    def in_category(cls):
        categories = getattr(cls, 'categories', ())
        cls.categories = categories + (name,)
        cls.add_to_category(CATEGORIES_TABLE, name, **kwargs)
        return cls
    return in_category


class SetsUpFixture(object):
    kind = FIXTURE
    SOURCE = None
    TARGET_FN = None
    module_name = None

    _fixture = None

    def __init__(self, root, directory, lineage):
        self.root = root
        self.directory = directory
        self.lineage = lineage

    @classmethod
    def add_to_category(cls, table, name, **kwargs):
        table[name][FIXTURE] = cls

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
                                      self.categories,
                                      module,
                                      path)
        return self._fixture

    def __repr__(self):
        cn = self.__class__.__name__
        return '{}(root={}, directory={}, lineage={})'.format(
            cn, self.root, self.directory, self.lineage)


class TestsForLoaderInCategory(object):
    kind = LOADER_TESTS
    loader = None
    should_fail = False
    this_version = True

    @classmethod
    def add_to_category(cls, table, name, **kwarg):
        table[name][LOADER_TESTS].append(cls)

    @classmethod
    def reset(cls):
        cls.loader = None

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

    @contextlib.contextmanager
    def assert_import_fails(self):
        with pytest.raises(ImportError):
            yield


def track_tests(module):
    module._TRACK_TESTS = []

    def track(Tests):
        module._TRACK_TESTS.append(Tests)
        return Tests

    return track


def reset_tests(module):
    for test in module._TRACK_TESTS:
        test.reset()


@in_category('package')
class PackageFixture(SetsUpFixture):
    TARGET_FN = '__init__.py'


@in_category('py_and_pyc')
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


@in_category('package')
@in_category('py_and_pyc')
class TestsForPyLoader(TestsForPurePythonLoaders):

    def assert_module_dot_files_equal(self, loaded, expected):
        super(TestsForPyLoader, self).assert_module_dot_files_equal(loaded,
                                                                    expected)
        assert py.path.local(loaded.__file__).ext == '.py'


@in_category('no_py')
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


@in_category('no_py')
class TestsForPyCompiledLoader(TestsForPurePythonLoaders):

    def assert_module_dot_files_equal(self, loaded, expected):
        super(TestsForPyCompiledLoader,
              self).assert_module_dot_files_equal(loaded, expected)
        assert py.path.local(loaded.__file__).ext == '.pyc'


@in_category('extension_module')
class SetsUpExtensionModule(SetsUpFixture):
    module_name = '{}c'.format(PY_TAG)

    SO_SRC_DIR = FIXTURES_SOURCE.join(PY_TAG)
    SO_BUILD_DIR = 'build'
    TARGET_FN = '{}.so'.format(module_name)
    SOURCE = py.path.local(SO_SRC_DIR).join(SO_BUILD_DIR).join(TARGET_FN)

    def create(self):
        if self.SOURCE.exists():
            return
        orig_dir = os.getcwd()
        try:
            os.chdir(str(self.SO_SRC_DIR))
            subprocess.check_call([sys.executable,
                                   'setup.py',
                                   'build',
                                   '--build-lib',
                                   self.SO_BUILD_DIR])
        finally:
            os.chdir(orig_dir)

    def install(self, location):
        self.SOURCE.copy(location)


@in_category('extension_module')
class TestsForExtensionModule(TestsForLoaderInCategory):

    def assert_module_dot_files_equal(self, loaded, actual):
        pass


@in_category('bad_pyc')
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


@in_category('package')
@in_category('py_and_pyc')
class TestsForTryPycThenPyLoader(TestsForPyCompiledLoader):
    this_version = IS_PYTHON_27


@in_category('bad_pyc')
class TestsForPycWithBadMagicNumber(TestsForLoaderInCategory):
    should_fail = True
    this_version = IS_PYTHON_27


def all_lineages(deepest_lineage):
    generations = deepest_lineage.split('.')
    return [tuple(generations[:i]) for i in range(len(generations) + 1)]


def category_fixture_loaders(root, directory, lineage):
    if not lineage:
        # top level fixtures
        relevant_categories = CATEGORIES - set(['package'])
    else:
        relevant_categories = CATEGORIES

    category_fixture_loaders = []
    for category in relevant_categories:
        for loader_tests in CATEGORIES_TABLE[category][LOADER_TESTS]:
            if not loader_tests.this_version:
                continue

            fixture_setup = CATEGORIES_TABLE[category][FIXTURE](root,
                                                                directory,
                                                                lineage)
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

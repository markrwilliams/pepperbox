import os
import subprocess
import sys
from collections import namedtuple
import imp
import importlib
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
LINEAGE = ('a', 'b', 'c', 'd')


class ModuleFixture(namedtuple('ModuleFixture',
                               'shortname category module path')):

    @property
    def package(self):
        return self.module.__name__.rpartition('.')[0]


class LoadModuleOrPackage(object):
    '''A context manager that loads a package or module.

    The module and any intermediate packages are available in
    sys.modules inside the with block.  They are removed after it terminates.

    :param directory: Path to the directory that contains the
                      requested module/package path.
    :param module_or_package_path: A dotted import path
    '''

    def __init__(self, directory, module_or_package_path):
        self.directory = directory
        self.module_or_package_path = module_or_package_path
        self.to_uncache = []

    def __enter__(self):
        fqn = self.module_or_package_path.split('.')
        path = [self.directory]
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

    def __exit__(self, *exc_info):
        for name in self.to_uncache:
            sys.modules.pop(name, None)

FIXTURE = 'FIXTURE'
LOADER = 'LOADER'

CATEGORIES = frozenset(['package',
                        'py_and_pyc',
                        'no_py',
                        'extension_module'])
CATEGORIES_TABLE = {k: {FIXTURE: [],
                        LOADER: []}
                    for k in CATEGORIES}


def in_category(name):
    assert name in CATEGORIES

    def in_category(cls):
        categories = getattr(cls, 'categories', ())
        cls.categories = categories + (name,)
        CATEGORIES_TABLE[name][cls.kind].append(cls)
        return cls
    return in_category


class SetsUpFixture(object):
    kind = FIXTURE
    module_name = None
    sources = ()

    def create(self):
        pass

    def ensure(self, directory, is_package=True):
        directory.ensure(dir=True)
        if is_package:
            # TODO: this is not fully testing the __init__ related code
            init = directory.join('__init__.py').ensure()
            py_compile.compile(str(init))

    def path(self, directory):
        raise NotImplementedError

    def install(self, directory):
        pass

    def load(self, directory, lineage):
        fqn = list(lineage)
        if self.module_name is not None:
            fqn.append(self.module_name)

        module_or_package = '.'.join(fqn)
        with LoadModuleOrPackage(str(directory), module_or_package) as mop:
            return mop

    def __call__(self, root, directory, lineage):
        self.ensure(directory, bool(lineage))
        path = self.path(directory)
        if path.exists():
            self.create()
            self.install(directory)
        module = self.load(root, lineage)

        if self.module_name is None:
            module_name = lineage[-1]
        else:
            module_name = self.module_name

        return ModuleFixture(module_name,
                             self.categories,
                             module,
                             path)


class TestsForLoaderInCategory(object):
    kind = LOADER

    @classmethod
    def set_loader(cls, path, classname):
        cls.loader = getattr(importlib.import_module(path), classname)

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


@in_category('package')
class PackageFixture(SetsUpFixture):

    def path(self, directory):
        # TODO: this is not fully testing the __init__ related code
        return directory.join('__init__.py')


@in_category('py_and_pyc')
class SetsUpPyAndPycFixture(SetsUpFixture):
    SOURCE = FIXTURES_SOURCE.join('py_and_pyc.py')
    module_name = 'py_and_pyc'

    def path(self, directory):
        return directory.join(self.SOURCE.basename)

    def install(self, location):
        dst = location.join(self.SOURCE.basename)
        self.SOURCE.copy(location)
        py_compile.compile(str(dst))


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
class SetsUpNoPyFixture(SetsUpFixture):
    SOURCE = FIXTURES_SOURCE.join('no_py.py')
    module_name = 'no_py'

    def path(self, directory):
        return directory.join(self.SOURCE.purebasename + '.pyc')

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
        dst = location.join(self.SOURCE.basename)
        self.SOURCE.copy(location)
        py_compile.compile(str(dst))

        if not IS_PYTHON_27:
            self._rename_python3_bytecode(dst)

        dst.remove()


@in_category('no_py')
class TestsForPyCompiledLoader(TestsForPurePythonLoaders):

    def assert_module_dot_files_equal(self, loaded, expected):
        super(TestsForPyCompiledLoader,
              self).assert_module_dot_files_equal(loaded, expected)
        assert py.path.local(loaded.__file__).ext == '.pyc'


@in_category('package')
@in_category('py_and_pyc')
class TestsForTryPycThenPyLoader(TestsForPyCompiledLoader):
    pass


@in_category('extension_module')
class SetsUpExtensionModule(SetsUpFixture):
    module_name = '{}c'.format(PY_TAG)

    SO_SRC_DIR = FIXTURES_SOURCE.join(PY_TAG)
    SO_BUILD_DIR = 'build'
    FILENAME = '{}.so'.format(module_name)
    SOURCE = py.path.local(SO_SRC_DIR).join(SO_BUILD_DIR).join(FILENAME)

    def path(self, directory):
        return directory.join(self.SOURCE.basename)

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


def set_up_fixtures(root, lineage=LINEAGE):
    modules_by_category = {}

    def establish_fixtures(category, directory, lineage):
        fixture = CATEGORIES_TABLE[category][FIXTURE][0]()
        modules_by_category.setdefault(category, []).append(
            fixture(root, directory, lineage))

    top_level_fixtures = CATEGORIES - set(['package'])

    for category in top_level_fixtures:
        establish_fixtures(category,
                           directory=root,
                           lineage=())

    directory = root
    for i, name in enumerate(lineage, 1):
        directory = directory.join(name)
        current_lineage = lineage[:i]

        for category in CATEGORIES:
            establish_fixtures(category, directory, current_lineage)

    return modules_by_category

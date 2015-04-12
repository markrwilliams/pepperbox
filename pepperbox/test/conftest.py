import os
import subprocess
import imp
import sys
from collections import namedtuple
import py.path
import pytest
import py_compile
from .common import IS_PYTHON_27


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

ModuleFixture = namedtuple('ModuleFixture', 'shortname category module path')


class FixtureCategory(object):
    name = None
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

        to_uncache = []
        path = [str(directory)]

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
            mod = imp.load_module(name, *spec)

            path = getattr(mod, '__path__', [])
            to_uncache.append(name)

        for u in to_uncache:
            sys.modules.pop(u, None)

        return mod

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
                             self.name,
                             module,
                             path)


class Package(FixtureCategory):
    name = 'package'

    def path(self, directory):
        # TODO: this is not fully testing the __init__ related code
        return directory.join('__init__.py')

package = Package()


class PyAndPyc(FixtureCategory):
    SOURCE = FIXTURES_SOURCE.join('py_and_pyc.py')
    name = 'py_and_pyc'
    module_name = 'py_and_pyc'

    def path(self, directory):
        return directory.join(self.SOURCE.basename)

    def install(self, location):
        dst = location.join(self.SOURCE.basename)
        self.SOURCE.copy(location)
        py_compile.compile(str(dst))


py_and_pyc = PyAndPyc()


class NoPy(FixtureCategory):
    SOURCE = FIXTURES_SOURCE.join('no_py.py')
    name = 'no_py'
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

no_py = NoPy()


class ExtensionModule(FixtureCategory):
    name = 'extension_module'
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


extension_module = ExtensionModule()


def make_modules_by_category(root, lineage=LINEAGE):
    modules_by_category = {}

    most_categories = (py_and_pyc, no_py, extension_module)
    all_categories = (package,) + most_categories

    def add_category(cat, *args, **kwargs):
        mod_fixture = cat(*args, **kwargs)
        modules_by_category.setdefault(cat.name, []).append(mod_fixture)

    for cat in most_categories:
        add_category(cat, root, root, lineage=())

    directory = root
    for i, name in enumerate(LINEAGE, 1):
        directory = directory.join(name)
        cur_lineage = lineage[:i]

        for cat in all_categories:
            add_category(cat, root, directory, lineage=cur_lineage)

    return modules_by_category


def pytest_addoption(parser):
    parser.addoption("--fixture-dir", action="store", default=None,
                     help='Directory in which the tests will write out '
                     "pepperbox's Python module and package fixtures.")


@pytest.fixture(scope='session')
def modules_by_category(request):
    fixture_dir = request.config.getoption('--fixture-dir')
    if fixture_dir is None:
        raise RuntimeError("--fixture-dir must be set!")

    fixture_dir = py.path.local(fixture_dir)
    return make_modules_by_category(fixture_dir)


_MISSING = object()


def pytest_generate_tests(metafunc):
    pyt_python = metafunc.config.pluginmanager.getplugin('python')

    try:
        markers = metafunc.function.parametrize_skipif
    except AttributeError:
        return

    for marker in markers:
        skipif = marker.kwargs.get('skipif', _MISSING)
        if skipif is _MISSING:
            raise pyt_python.MarkerError('parametrize_skipif needs skipif'
                                         ' kwarg')

    for marker in markers:
        if not marker.kwargs.pop('skipif'):
            for marker in markers:
                real_marker = marker.args[0]()
                metafunc.parametrize(*real_marker.args, **real_marker.kwargs)

    pyt_python.pytest_generate_tests(metafunc)

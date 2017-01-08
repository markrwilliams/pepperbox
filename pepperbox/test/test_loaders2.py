from itertools import chain, combinations
import operator
import functools
from contextlib import contextmanager
from collections import namedtuple
import imp
import py_compile
import py
import pytest
import sys
import subprocess

from pepperbox.support import DirectoryFD, PY_TAG
from . import common as C


def _calculate_lineages(deepest_lineage):
    generations = deepest_lineage.split('.')
    return [tuple(generations[:i]) for i in range(len(generations) + 1)]


LINEAGES = _calculate_lineages('a.b.c.d')

FIXTURES_SOURCE = py.path.local(__file__).dirpath('fixtures_src')


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
    sys.modules inside the with block.  They are removed after it
    terminates.

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


class ModuleFixture(namedtuple('ModuleFixture',
                               'shortname module path')):

    @property
    def package(self):
        return self.module.__name__.rpartition('.')[0]

    @classmethod
    def for_fixture(cls, fixture_dir, target_file, module_path):
        with LoadModuleOrPackage(str(fixture_dir),
                                 str(target_file),
                                 '.'.join(module_path)) as mop:

            return cls(shortname=module_path[-1],
                       module=mop,
                       path=target_file)


@pytest.fixture(scope='session')
def fixture_dir(request):
    path = py.path.local(request.config.getoption('fixture_dir'))
    path.ensure(dir=1)
    return path


@pytest.fixture(scope='session', params=LINEAGES)
def lineage(request):
    return request.param


def create_package(fixture_dir, lineage):
    target_dir = fixture_dir.join(*lineage)
    __init__ = None
    if lineage:
        __init__ = target_dir.join('__init__.py')
        if not __init__.exists():
            __init__.ensure()
            py_compile.compile(str(__init__))
    return target_dir, __init__


def ensure_package(fixture_dir, lineage):
    target_dir, _ = create_package(fixture_dir, lineage)
    return target_dir


def loader_fixture(f):
    cache = {}

    @functools.wraps(f)
    def wrapped():

        @functools.wraps(f)
        def fixture(lineage, fixture_dir):
            args = (lineage, str(fixture_dir))
            cached = cache.get(args)
            if not cached:
                cache[args] = cached = f(*args)
            return cached

        return fixture

    return pytest.fixture(scope='session')(wrapped)


@loader_fixture
def package(lineage, fixture_dir):
    if not lineage:
        return pytest.skip("not installed into the top level directory")

    _, target_file = create_package(fixture_dir, lineage)

    module_path = list(lineage)
    return ModuleFixture.for_fixture(fixture_dir, target_file, module_path)


@loader_fixture
def py_and_pyc(lineage, fixture_dir):
    target_dir = ensure_package(fixture_dir, lineage)
    target_file = target_dir.join('py_and_pyc.py')

    if not target_file.exists():
        FIXTURES_SOURCE.join(target_file.basename).copy(target_file)

    if not target_dir.join('py_and_pyc.pyc').exists():
        py_compile.compile(str(target_file))

    module_path = list(lineage) + ['py_and_pyc']

    return ModuleFixture.for_fixture(fixture_dir, target_file, module_path)


@loader_fixture
def no_py(lineage, fixture_dir):
    target_dir = ensure_package(fixture_dir, lineage)

    pure_python = target_dir.join('no_py.py')
    target_file = py.path.local(str(pure_python).replace('.py', '.pyc'))

    if not target_file.exists():
        FIXTURES_SOURCE.join(pure_python.basename).copy(pure_python)

        py_compile.compile(str(pure_python))
        pure_python.remove()

        if not C.IS_PYTHON_27:
            # "If the py source file is missing, the pyc file inside
            # __pycache__ will be ignored. This eliminates the problem of
            # accidental stale pyc file imports."
            # https://www.python.org/dev/peps/pep-3147/
            from importlib.util import cache_from_source
            bytecode = py.path.local(cache_from_source(str(pure_python)))
            bytecode.copy(target_file)

    module_path = list(lineage) + ['no_py']

    return ModuleFixture.for_fixture(fixture_dir, target_file, module_path)


@loader_fixture
def py_with_out_of_date_pyc(lineage, fixture_dir):
    target_dir = ensure_package(fixture_dir, lineage)

    pure_python = target_dir.join('py_with_out_of_date_pyc.py')
    target_file = py.path.local(str(pure_python).replace('.py', '.pyc'))

    if not target_file.exists():



@loader_fixture
def extension_module(lineage, fixture_dir):
    target_dir = ensure_package(fixture_dir, lineage)

    module_name = '{}c'.format(PY_TAG)
    target_basename = '{}.so'.format(module_name)
    target_file = target_dir.join(target_basename)

    if not target_file.exists():
        source_dir = FIXTURES_SOURCE.join(PY_TAG)
        build_dir = source_dir.join('build')
        built_so = build_dir.join(target_basename)
        if not built_so.exists():
            subprocess.check_call(
                [sys.executable,
                 'setup.py', 'build', '--build-lib', str(build_dir)],
                cwd=str(source_dir))
        built_so.copy(target_file)

    module_path = list(lineage) + [module_name]

    return ModuleFixture.for_fixture(fixture_dir, target_file, module_path)


@pytest.fixture(scope='session')
def pure_python_loader():
    if C.IS_PYTHON_27:
        from pepperbox.py27.loader import PyOpenatLoader as Loader
    else:
        from pepperbox.py34.loader import OpenatSourceFileLoader as Loader
    return Loader


@pytest.fixture(scope='session')
def bytecode_loader():
    if C.IS_PYTHON_27:
        from pepperbox.py27.loader import PyCompiledOpenatLoader as Loader
    else:
        from pepperbox.py34.loader import OpenatSourcelessFileLoader as Loader
    return Loader


@pytest.fixture(scope='session')
def try_bytecode_then_python_loader():
    if C.IS_PYTHON_27:
        from pepperbox.py27.loader import TryPycThenPyOpenatLoader
        return TryPycThenPyOpenatLoader
    else:
        return pytest.skip("python 2.7")


@pytest.fixture(scope='session')
def extension_loader():
    if C.IS_PYTHON_27:
        from pepperbox.py27.loader import RTLDOpenatLoader as Loader
    else:
        from pepperbox.py34.loader import OpenatExtensionFileLoader as Loader
    return Loader


@pytest.fixture(scope='session',
                params=['pure_python_loader',
                        'try_bytecode_then_python_loader'])
def python_loader_category(request):
    return request.getfuncargvalue(request.param)


@pytest.fixture(scope='session',
                params=['try_bytecode_then_python_loader',
                        'bytecode_loader'])
def bytecode_loader_category(request):
    return request.getfuncargvalue(request.param)


@pytest.fixture(scope='session', params=['extension_loader'])
def extension_loader_category(request):
    return request.getfuncargvalue(request.param)


@pytest.fixture(scope='session',
                params=['package',
                        'py_and_pyc',
                        'no_py'])
def python_test_module(request):
    return request.getfuncargvalue(request.param)


@pytest.fixture(scope='session')
def module_finder():
    if C.IS_PYTHON_27:
        from pepperbox.py27.loader import OpenatFileFinder
    else:
        from pepperbox.py34.loader import OpenatFileFinder
    return OpenatFileFinder


@contextmanager
def MaybeLoadParentPackage(fixture_dir, fixture):
    if C.IS_PYTHON_27 and fixture.package:
        # because of the particulars of setting module.__package__ in
        # python 2, we need to make sure the immediate parents of this
        # module or package are available in sys.modules
        with LoadModuleOrPackage(str(fixture_dir),
                                 str(fixture.path),
                                 fixture.package):
            yield
    else:
        yield


def test_me(fixture_dir, lineage, python_loader, test_module):
    print fixture_dir, lineage, python_loader, test_module


def test_python_loaders(fixture_dir, python_loader, fixture):
    module_name = fixture.module.__name__
    directory = fixture.path.dirname
    loader = python_loader(module_name,
                           str(fixture.path),
                           DirectoryFD(directory))

    with MaybeLoadParentPackage(fixture_dir, fixture):
        module = loader.load_module(module_name)

    assert module.__name__ == module_name
    assert module.__package__ == fixture.module.__package__


def test_python_loaders_and_package(fixture_dir,
                                    python_loader,
                                    package):
    _test_python_loader(fixture_dir, python_loader, package)


# def test_python_loaders_and_py_and_pyc(fixture_dir,
#                                        python_loader,
#                                        py_and_pyc):
#     _test_python_loader(fixture_dir, python_loader, py_and_pyc)


# def test_bytecode_loader(fixture_dir, bytecode_loader, no_py):
#     _test_python_loader(fixture_dir, bytecode_loader, no_py)


# def test_extension_loader(fixture_dir, extension_loader, extension_module):
#     _test_python_loader(fixture_dir, extension_loader, extension_module)


# def _test_module_finder(fixture_dir, Finder, fixture, Loader,
#                         should_fail=False):
#     module_name = fixture.module.__name__
#     package = fixture.package

#     finder = Finder(str(fixture_dir), rights=())

#     if C.IS_PYTHON_27:
#         find_module = functools.partial(finder.find_module, module_name)
#         get_loader = lambda loader: loader
#     else:
#         # python 3.4 has specs, so we have to have some indirection
#         find_module = functools.partial(finder.find_spec, module_name)
#         get_loader = operator.attrgetter('loader')

#     if not package:
#         result = find_module()
#     else:
#         # find our parent package
#         parent_package = package.rpartition('.')[-1]
#         # find its path
#         package_path = fixture.path.pypkgpath(parent_package)
#         # make sure we pass that to find_module
#         result = find_module(path=[str(package_path)])

#     if should_fail:
#         assert result is None
#     else:
#         loader = get_loader(result)
#         assert isinstance(loader, Loader)

#         expected_no_ext = fixture.path.dirpath(fixture.path.purebasename)

#         actual_no_ext = py.path.local(loader.path)
#         actual_no_ext = actual_no_ext.dirpath(actual_no_ext.purebasename)

#         assert actual_no_ext == expected_no_ext


# @C.only_py27
# def test_finder_package_py27(fixture_dir,
#                              module_finder,
#                              package,
#                              try_bytecode_then_python_loader):
#     _test_module_finder(fixture_dir,
#                         module_finder,
#                         package,
#                         try_bytecode_then_python_loader)


# @C.only_py34
# def test_finder_package_pure_python_loader(fixture_dir,
#                                            module_finder,
#                                            package,
#                                            pure_python_loader):
#     _test_module_finder(fixture_dir,
#                         module_finder,
#                         package,
#                         pure_python_loader)


# def test_finder_no_py(fixture_dir,
#                       module_finder,
#                       no_py,
#                       bytecode_loader):
#     _test_module_finder(fixture_dir,
#                         module_finder,
#                         no_py,
#                         bytecode_loader)


# def test_finder_extension(fixture_dir,
#                           module_finder,
#                           extension_module,
#                           extension_loader):
#     _test_module_finder(fixture_dir,
#                         module_finder,
#                         extension_module,
#                         extension_loader)

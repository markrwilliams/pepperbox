import imp
from collections import namedtuple
import py.path
import pytest
import py_compile


class PackageDirectoryTree(object):

    def __init__(self, root):
        self.root = root
        self.packages = {}
        self.modules = {}
        self.packages_by_category = {}
        self.modules_by_category = {}

    def import_module(self, path, lineage):
        name = '.'.join(lineage)
        shortname = lineage[-1]
        str_path = str(path.join('..'))
        mod = imp.load_module(name, *imp.find_module(shortname,
                                                     [str_path]))
        return name, mod

    def shortname(self, module):
        return module.rpartition('.')[-1]

    def add_package(self, path, lineage, category):
        name, mod = self.import_module(path, lineage)
        self.packages[name] = (py.path.local(mod.__file__), mod)
        self.packages_by_category.setdefault(category, []).append(name)
        return name

    def add_module(self, path, lineage, category):
        name, mod = self.import_module(path, lineage)
        self.modules[name] = (py.path.local(mod.__file__), mod)
        self.modules_by_category.setdefault(category, []).append(name)
        return name


class ModuleFixture(namedtuple('ModuleFixture', 'name path')):

    @property
    def category(self):
        return self.name


def prep_pure_python(fixtures, tmpdir):
    fixtures.join('py_and_pyc.py').copy(tmpdir)
    return ModuleFixture('py_and_pyc', tmpdir.join('py_and_pyc.py'))


def prep_pure_bytecode(fixtures, tmpdir):
    fixtures.join('no_py.py').copy(tmpdir)
    pure_bytecode_src = tmpdir.join('no_py.py')
    py_compile.compile(str(pure_bytecode_src))
    pure_bytecode_src.remove()
    return ModuleFixture('no_py', tmpdir.join('no_py.pyc'))


def prep_modules(tmpdir):
    FUNCS = [prep_pure_python, prep_pure_bytecode]
    fixtures = py.path.local(py.path.local(__file__).dirname).join('fixtures')
    return [f(fixtures, tmpdir) for f in FUNCS]


@pytest.fixture
def package_directory_tree(tmpdir):
    modules = prep_modules(tmpdir)
    tree = PackageDirectoryTree(tmpdir)

    parent = tmpdir
    lineage = []

    for mod_fixture in modules:
        tree.add_module(mod_fixture.path, [mod_fixture.name],
                        category=mod_fixture.category)

    for package in ('a', 'b', 'c', 'd'):
        lineage.append(package)
        package_path = parent.mkdir(package)
        package_path.ensure('__init__.py')

        name = tree.add_package(package_path, lineage, category='py_and_pyc')

        for mod_fixture in modules:
            mod_fixture.path.copy(package_path)
            mod_path_to = package_path.join(package_path.basename)
            tree.add_module(mod_path_to, lineage + [mod_fixture.name],
                            category=mod_fixture.category)

        parent = package_path

    return tree


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

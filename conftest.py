import imp
import py.path
import pytest
import py_compile


class PackageDirectoryTree(object):

    def __init__(self, root):
        self.root = root
        self.packages = {}
        self.modules = {}
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

    def add_package(self, path, lineage):
        name, mod = self.import_module(path, lineage)
        self.packages[name] = (py.path.local(mod.__file__), mod)

    def add_module(self, path, lineage, category=None):
        name, mod = self.import_module(path, lineage)
        self.modules[name] = (py.path.local(mod.__file__), mod)
        if category:
            self.modules_by_category.setdefault(category, []).append(name)


def prep_pure_python(fixtures, tmpdir):
    fixtures.join('no_pyc.py').copy(tmpdir)
    return 'no_pyc', tmpdir.join('no_pyc.py')


def prep_pure_bytecode(fixtures, tmpdir):
    fixtures.join('no_py.py').copy(tmpdir)
    pure_bytecode_src = tmpdir.join('no_py.py')
    py_compile.compile(str(pure_bytecode_src))
    pure_bytecode_src.remove()
    return 'no_py', tmpdir.join('no_py.pyc')


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

    for mod_name, mod_path_from in modules:
        tree.add_module(mod_path_from, [mod_name], category=mod_name)

    for package in ('a', 'b', 'c', 'd'):
        lineage.append(package)
        package_path = parent.mkdir(package)
        package_path.ensure('__init__.py')

        tree.add_package(package_path, lineage)

        for mod_name, mod_path_from in modules:
            mod_path_from.copy(package_path)
            mod_path_to = package_path.join(package_path.basename)
            tree.add_module(mod_path_to, lineage + [mod_name],
                            category=mod_name)

        parent = package_path

    return tree

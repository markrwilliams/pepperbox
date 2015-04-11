import sys
import py_compile
import shutil
import os
import subprocess


VERSION = 'py%s%s' % sys.version_info[:2]


PACKAGE_NAMES = ('a', 'b', 'c', 'd')
PY_AND_PYC = '_fixtures_src/py_and_pyc.py'
NO_PYC = '_fixtures_src/no_py.py'

SO_SRC_DIR = os.path.join('_fixtures_src', VERSION)
SO_BUILD_DIR = 'build'
SO = os.path.join(SO_SRC_DIR, SO_BUILD_DIR, '%sc.so' % VERSION)


def make_package(package, compile=True):
    init = os.path.join(package, '__init__.py')
    print("creating", init)
    with open(init, 'w'):
        pass
    if compile:
        py_compile.compile(init)


def make_py_and_pyc(dst, src=PY_AND_PYC):
    target = os.path.join(dst, os.path.basename(src))
    print("creating", target)
    shutil.copy2(src, dst)
    py_compile.compile(target)


def _rename_python3_bytecode(pure_python):
    # "If the py source file is missing, the pyc file inside
    # __pycache__ will be ignored. This eliminates the problem of
    # accidental stale pyc file imports."
    # https://www.python.org/dev/peps/pep-3147/
    from importlib.util import cache_from_source
    bytecode = cache_from_source(pure_python)

    target_dir = os.path.dirname(pure_python)
    target_fn = os.path.basename(pure_python)

    target_fn = target_fn.replace('.py', '.pyc')
    target = os.path.join(target_dir, target_fn)

    shutil.copy2(bytecode, target)
    return target


def make_no_py(dst, src=NO_PYC):
    target = os.path.join(dst, os.path.basename(src))
    shutil.copy2(src, dst)
    py_compile.compile(target)
    os.remove(target)

    if sys.version_info.major > 2:
        print("created", _rename_python3_bytecode(target))


def compile_so(src=SO):
    if not os.path.isfile(SO):
        orig_dir = os.getcwd()
        try:
            os.chdir(SO_SRC_DIR)
            subprocess.check_call([sys.executable,
                                   'setup.py',
                                   'build',
                                   '--build-lib',
                                   SO_BUILD_DIR])
        finally:
            os.chdir(orig_dir)


def make_so(dst, src=SO):
    target = os.path.join(dst, os.path.basename(src))
    print("creating", target)
    shutil.copy2(src, dst)


def create_packages(start='test_%s_loader' % VERSION):
    if not os.path.isdir(start):
        os.makedirs(start)

    make_py_and_pyc(start)
    make_no_py(start)
    make_so(start)

    pkg = start
    for name in PACKAGE_NAMES:
        pkg = os.path.join(pkg, name)
        if not os.path.isdir(pkg):
            os.makedirs(pkg)

        make_package(pkg)
        make_py_and_pyc(pkg)
        make_no_py(pkg)
        make_so(pkg)

if __name__ == '__main__':
    compile_so()
    create_packages()

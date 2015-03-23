import pytest
import sys
import os
from pepperbox.support import DirectoryFD


def py27(f):
    return pytest.mark.skipif(sys.version_info.major > 2,
                              reason='only for Python 2.7')(f)


@pytest.fixture
def loader():
    from pepperbox.py27 import loader
    return loader


@py27
def test_PyOpenatLoader_module_succeeds(loader):
    test_fn = os.path.join(os.path.dirname(__file__), 'no_pyc.py')
    test_fn_bytecode = test_fn.replace('.py', '.pyc')

    head = test_fn
    args = ()
    while head != os.path.sep:
        head, new_tail = os.path.split(head)
        if not head:
            break

        args = (new_tail,) + args
        tail = os.path.join(*args)

        dirobj = DirectoryFD(head)
        pol = loader.PyOpenatLoader(head, dirobj, tail, is_package=False)
        module = pol.load_module('no_pyc')
        assert module
        assert module.contents == 'no pyc'
        assert not os.path.exists(test_fn_bytecode)


@py27
def test_PyOpenatLoader_inaccessible_module_fails(tmpdir, loader):
    with pytest.raises(ImportError):
        missing_pol = loader.PyOpenatLoader(str(tmpdir),
                                            DirectoryFD(str(tmpdir)),
                                            'missing.py',
                                            is_package=False)
        missing_pol.load_module('missing')

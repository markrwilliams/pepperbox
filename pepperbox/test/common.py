import sys
import py
import pytest

IS_PYTHON_27 = sys.version_info.major == 2 and sys.version_info.minor == 7
IS_PYTHON_34 = sys.version_info.major == 3 and sys.version_info.minor == 4

only_py27 = pytest.mark.skipif(not IS_PYTHON_27, reason='only for Python 2.7')
only_py34 = pytest.mark.skipif(not IS_PYTHON_34, reason='only for Python 3.4')


def mod__files__equal(loaded, actual):
    assert loaded.__file__ == actual.__file__

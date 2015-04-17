import py.path
import pytest
from .common import gen_category_fixture_loaders


def pytest_namespace():
    return {'pepperbox_loader_table': []}


def pytest_addoption(parser):
    parser.addoption("--fixture-dir", action="store", default=None,
                     help='Directory in which the tests will write out '
                     "pepperbox's Python module and package fixtures.")
    parser.addoption('--lineage', default='a.b.c.d',
                     help='import path representing the deepest package'
                     ' to create.')


def pytest_configure(config):
    fixture_dir = py.path.local(config.getoption('fixture_dir'))
    lineage = config.getoption('lineage')
    loader_table = gen_category_fixture_loaders(fixture_dir, lineage)
    pytest.pepperbox_loader_table = loader_table

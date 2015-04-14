import py.path
import pytest
from .common import set_up_fixtures


def pytest_addoption(parser):
    parser.addoption("--fixture-dir", action="store", default=None,
                     help='Directory in which the tests will write out '
                     "pepperbox's Python module and package fixtures.")


@pytest.fixture(scope='session')
def modules_by_category(request):
    fixture_dir = request.config.getoption('--fixture-dir')
    if fixture_dir is None:
        raise RuntimeError("--fixture-dir must be set!")

    return set_up_fixtures(py.path.local(fixture_dir))

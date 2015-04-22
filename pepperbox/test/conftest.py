def pytest_addoption(parser):
    parser.addoption("--fixture-dir", action="store", default=None,
                     help='Directory in which the tests will write out '
                     "pepperbox's Python module and package fixtures.")
    parser.addoption('--lineage', default='a.b.c.d',
                     help='import path representing the deepest package'
                     ' to create.')

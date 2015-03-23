import pytest
from pepperbox import support as S


class FileForTesting(object):
    name = 'test.txt'
    contents = b'contents'

    def __init__(self, tmpdir):
        self.dir = tmpdir
        self.path = tmpdir.join(self.name)
        self.path.write(self.contents)

    def paths(self):
        for path in self.name, str(self.path):
            yield path


@pytest.fixture
def test_file(tmpdir):
    return FileForTesting(tmpdir)


@pytest.fixture
def dirobj(request, test_file):
    return S.DirectoryFD(str(test_file.dir))


def test_DirectoryFD_closed(dirobj):
    assert not dirobj.closed
    dirobj.close()
    assert dirobj.closed


def test_DirectoryFD_handle_abspath(test_file, dirobj):
    for path in test_file.paths():
        assert test_file.name == dirobj.handle_abspath(path)

    with pytest.raises(S.BadPath):
        dirobj.handle_abspath('/abcd')


def test_DirectoryFD_open(test_file, dirobj):
    for path in test_file.paths():
        with dirobj.open(path) as f:
            assert f.read() == test_file.contents

        with pytest.raises(S.BadMode):
            dirobj.open(path, 'w')


def test_DirectoryFD_opendir(tmpdir):
    subdir_name = 'subdir'
    subdir = tmpdir.mkdir(subdir_name)

    for path in subdir_name, str(subdir):
        with S.DirectoryFD(str(tmpdir)).opendir(subdir_name) as f:
            assert isinstance(f, S.DirectoryFD)


def test_DirectoryFD_stat(test_file, dirobj):
    for path in test_file.paths():
        st = dirobj.stat(path)
        assert st.st_size == len(test_file.contents)


def test_DirectoryFD_exists(test_file, dirobj):
    for path in test_file.paths():
        missing_path = path + '.missing'
        assert dirobj.exists(str(test_file.path))
        assert dirobj.exists(path)
        assert not dirobj.exists(missing_path)


def test_DirectoryFD_isfile(test_file, dirobj):
    for path in test_file.paths():
        missing_path = path + '.missing'

        assert not dirobj.isfile(str(test_file.dir))
        assert not dirobj.isfile(missing_path)
        assert dirobj.isfile(path)


def test_DirectoryFD_isdir(test_file, dirobj):
    for path in test_file.paths():
        missing_path = path + '.missing'

        assert dirobj.isdir(str(test_file.dir))
        assert not dirobj.isdir(missing_path)
        assert not dirobj.isdir(path)


def test_DirectoryFD_listdir(test_file, dirobj):
    assert dirobj.listdir() == [test_file.name]

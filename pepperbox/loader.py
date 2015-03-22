import sys
import os


if sys.version_info.major > 2:
    from .py34.loader import OpenatFileFinder
else:
    from .py27.loader import OpenatFileFinder


def install(rights, preimports=()):
    for preimport in preimports:
        __import__(preimport)
    meta_path = [OpenatFileFinder(entry, rights)
                 for entry in sys.path
                 if entry and os.path.isdir(entry)]
    sys.meta_path = meta_path

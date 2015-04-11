from setuptools import setup, Extension

py27_ext = Extension('py27c',
                     sources=['py27cmodule.c'])

setup(name='py27c',
      version='1.0',
      ext_modules=[py27_ext])

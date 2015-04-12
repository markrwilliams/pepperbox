from setuptools import setup, Extension

py34_ext = Extension('py34c',
                     sources=['py34cmodule.c'])

setup(name='py34c',
      version='1.0',
      ext_modules=[py34_ext])

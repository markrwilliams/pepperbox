from setuptools import setup, Extension

cpython_27_ext = Extension('cpython_27c',
                           sources=['cpython_27cmodule.c'])

setup(name='cpython_27c',
      version='1.0',
      ext_modules=[cpython_27_ext])

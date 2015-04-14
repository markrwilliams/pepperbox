from setuptools import setup, Extension

cpython_34_ext = Extension('cpython_34c',
                           sources=['cpython_34cmodule.c'])

setup(name='cpython_34c',
      version='1.0',
      ext_modules=[cpython_34_ext])

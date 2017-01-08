if __name__ == '__main__':
    import os
    import sys
    from setuptools import setup, find_packages

    kwargs = {}
    if os.environ.get('INSTALL_CUSTOMIZE'):
        kwargs['pymodules'] = ['sitecustomize']

    with open('requirements{}.txt'.format(sys.version_info.major)) as f:
        requirements = list(f)

    setup(name='pepperbox',
          version='0.0.1',
          zip_safe=False,
          install_requires=requirements,
          cffi_modules=['pepperbox/_binding_build.py:ffi'],
          setup_requires=['cffi>=1.0.1'],
          include_package_data=True,
          packages=find_packages(),
          **kwargs)

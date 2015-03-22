if __name__ == '__main__':
    import os
    import sys
    from setuptools import setup, find_packages
    from pepperbox._ffi import ffi

    kwargs = {}
    if os.environ.get('INSTALL_CUSTOMIZE'):
        kwargs['pymodules'] = ['sitecustomize']

    with open('requirements{}.txt'.format(sys.version_info.major)) as f:
        requirements = list(f)

    setup(name='pepperbox',
          version='0.0.1',
          zip_safe=False,
          install_requires=requirements,
          packages=find_packages(),
          ext_package='pepperbox',
          ext_modules=[ffi.verifier.get_extension()],
          **kwargs)

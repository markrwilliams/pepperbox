from ._binding import ffi, lib


RTLD_NOW = lib.RTLD_NOW


def fdlopen(fd, flags):
    loaded_so = lib.fdlopen(fd, lib.RTLD_NOW)
    if loaded_so == ffi.NULL:
        raise RuntimeError(ffi.string(lib.dlerror()))
    return loaded_so


def dlsym(loaded_so, symname):
    void_ptr = lib.dlsym(loaded_so, symname)
    if void_ptr == ffi.NULL:
        raise RuntimeError(ffi.string(lib.dlerror()))
    return void_ptr


def make_callable_with_gil(initmodulefunc):
    def callable_with_gil(void_ptr):
        addr = lib.addrof(void_ptr)
        return initmodulefunc(addr)
    return callable_with_gil

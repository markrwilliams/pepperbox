import cffi
import ctypes


ffi = cffi.FFI()

ffi.cdef('''
static const int RTLD_NOW;
static const int RTLD_LAZY;

void *
fdlopen(int fd, int mode);

void *
dlsym(void * restrict handle, const char * restrict symbol);

char *
dlerror(void);

uintptr_t
addrof(void * f);

''')


lib = ffi.verify('''
#include <dlfcn.h>


uintptr_t
addrof(void * p){
    return (uintptr_t)p;
}
''',
                 ext_package='pepperbox')

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


INITMODULEFUNC = ctypes.PYFUNCTYPE(None)


def callable_with_gil(void_ptr):
    addr = lib.addrof(void_ptr)
    return INITMODULEFUNC(addr)

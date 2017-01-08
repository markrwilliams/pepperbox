import cffi

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


ffi.set_source('pepperbox._binding',
               '''
#include <dlfcn.h>


uintptr_t
addrof(void * p)
{
    return (uintptr_t)p;
}
''')

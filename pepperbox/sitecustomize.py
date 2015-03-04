def restrict():
    import os
    if os.environ.get('UNRESTRICT'):
        return
    import sys
    import resource
    import spyce
    import pepperbox.loader

    rights = spyce.Rights([spyce.CAP_READ,
                           spyce.CAP_LOOKUP,
                           spyce.CAP_FSTAT,
                           spyce.CAP_SEEK,
                           spyce.CAP_MMAP_RX,
                           spyce.CAP_MMAP,
                           spyce.CAP_FCNTL,
                           spyce.CAP_FSTATFS])

    def limitResource(thing, soft, hard=None):
        hard = hard or soft
        resource.setrlimit(thing, (soft, hard))

    limitResource(resource.RLIMIT_CPU, 9, 11)
    limitResource(resource.RLIMIT_AS, 512 * 1024 * 1024)
    limitResource(resource.RLIMIT_DATA, 512 * 1024 * 1024)
    limitResource(resource.RLIMIT_FSIZE, 10 * 1024 * 1024)
    limitResource(resource.RLIMIT_MEMLOCK, 0)
    limitResource(resource.RLIMIT_NPROC, 0)

    pepperbox.loader.install(rights=None, preimports=('random',))
    spyce.enterCapabilityMode()

    for module in ('resource', 'spyce', 'pepperbox'):
        del sys.modules[module]

def restrict():
    import resource
    import termios
    import spyce
    import pepperbox.loader

    rights = spyce.Rights([spyce.CAP_READ,
                           spyce.CAP_LOOKUP,
                           spyce.CAP_FSTAT,
                           spyce.CAP_SEEK,
                           spyce.CAP_MMAP_RX,
                           spyce.CAP_MMAP,
                           spyce.CAP_FCNTL,
                           spyce.CAP_IOCTL,
                           spyce.CAP_FSTATFS])

    ioctlRights = spyce.IoctlRights([termios.FIOCLEX])

    def limitResource(thing, soft, hard=None):
        hard = hard or soft
        resource.setrlimit(thing, (soft, hard))

    limitResource(resource.RLIMIT_CPU, 9, 11)
    limitResource(resource.RLIMIT_AS, 512 * 1024 * 1024)
    limitResource(resource.RLIMIT_DATA, 512 * 1024 * 1024)
    limitResource(resource.RLIMIT_FSIZE, 10 * 1024 * 1024)
    limitResource(resource.RLIMIT_MEMLOCK, 0)
    limitResource(resource.RLIMIT_NPROC, 0)

    pepperbox.loader.install(rights=(rights, ioctlRights),
                             preimports=('random',))
    spyce.enterCapabilityMode()

"""Kernel-enforced child restrictions on the deployed Linux runtime.

The private Lambda additionally runs in a VPC without routes or DNS and has
no data-service permissions. Local macOS execution is for trusted tests only.
"""

def restrict_child():
    import ctypes
    import errno
    import platform
    import sys
    if sys.platform != "linux":
        return
    machine = platform.machine()
    if machine == "x86_64":
        architecture = 0xC000003E
        denied = [41, 53, 56, 57, 58, 59, 62, 101, 200, 234, 272, 308, 310, 311, 322, 425, 426, 427, 435]
    elif machine == "aarch64":
        architecture = 0xC00000B7
        denied = [198, 199, 220, 221, 129, 130, 131, 117, 97, 268, 270, 271, 281, 425, 426, 427, 435]
    else:
        raise RuntimeError("unsupported sandbox architecture")
    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]
    # Validate ABI, reject x32/future syscalls, then deny networking, child
    # creation, process signalling/inspection, namespace changes and io_uring.
    instructions = [(0x20, 0, 0, 4), (0x15, 1, 0, architecture), (0x06, 0, 0, 0x80000000),
                    (0x20, 0, 0, 0), (0x35, 0, 1, 512), (0x06, 0, 0, 0x00050000 | errno.EPERM)]
    for syscall in denied:
        instructions.extend([(0x15, 0, 1, syscall), (0x06, 0, 0, 0x00050000 | errno.EPERM)])
    instructions.append((0x06, 0, 0, 0x7FFF0000))
    filters = (Filter * len(instructions))(*(Filter(*row) for row in instructions))
    program = Program(len(instructions), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:
        raise RuntimeError("cannot install execution sandbox")

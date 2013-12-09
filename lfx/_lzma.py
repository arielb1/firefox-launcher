from ctypes import *

as_char_p = lambda a: cast(addressof(a), POINTER(c_ubyte))
as_void_p = lambda a: cast(addressof(a), c_void_p)

_lib = CDLL('liblzma.so.2')

uint32_t = c_uint if sizeof(c_uint) == 4 else c_ulong
uint64_t = lzma_vli = c_ulonglong
uint8_t = lzma_bool = c_ubyte

MODE_FAST = 1
MODE_NORMAL = 2
mode = c_uint

MF_HC4 = 0x04
MF_BT4 = 0x14
match_finder = c_uint

RUN = 0
SYNC_FLUSH = 1
FULL_FLUSH = 2
FINISH = 3
action = c_uint

OK = 0
STREAM_END = 1
ret = c_uint

DICT_SIZE_MIN = 4096
DICT_SIZE_DEFAULT = 1<<23

VLI_UNKNOWN = lzma_vli(-1 % (1<<64))

FILTER_LZMA2 = lzma_vli(0x21)
FILTER_UNKNOWN = VLI_UNKNOWN

def reserved(name, t, num):
    return [('reserved_{}{}'.format(name, i), t) for i in range(num)]

class options_lzma(Structure):
    _fields_ = [('dict_size', uint32_t),
                ('preset_dict', POINTER(c_ubyte)),
                ('preset_dict_size', uint32_t),
                ('lc', uint32_t),
                ('lp', uint32_t),
                ('pb', uint32_t),
                ('mode', mode),
                ('nice_len', uint32_t),
                ('mf', match_finder),
                ('depth', uint32_t),
                ] + reserved('int', uint32_t, 8
                ) + reserved('enum', c_uint, 4
                ) + reserved('ptr', c_void_p, 2
                )

class filter(Structure):
    _fields_ = [('id', lzma_vli),
                ('options', c_void_p)
                ]

class allocator(Structure):
    pass

class internal(Structure):
    pass

class stream(Structure):
    _fields_ = [('next_in', POINTER(uint8_t)),
                ('avail_in', c_size_t),
                ('total_in', uint64_t),

                ('next_out', POINTER(uint8_t)),
                ('avail_out', c_size_t),
                ('total_out', uint64_t),

                ('allocator', POINTER(allocator)),
                ('internal', POINTER(internal)),
                ] + reserved('ptr', c_void_p, 4
                ) + reserved('int', uint64_t, 2
                ) + reserved('szt', c_size_t, 2
                ) + reserved('enum', c_uint, 2)

lzma_preset = _lib.lzma_lzma_preset
lzma_preset.restype = lzma_bool
lzma_preset.argtypes = [POINTER(options_lzma), uint32_t]

raw_encoder = _lib.lzma_raw_encoder
raw_encoder.restype = ret
raw_encoder.argtypes = [POINTER(stream), POINTER(filter)]

raw_decoder = _lib.lzma_raw_decoder
raw_decoder.restype = ret
raw_decoder.argtypes = [POINTER(stream), POINTER(filter)]

code = _lib.lzma_code
code.restype = ret
code.argtypes = [POINTER(stream), action]

end = _lib.lzma_end
end.restype = None
end.argtypes = [POINTER(stream)]

memusage = _lib.lzma_memusage
memusage.restype = uint64_t
memusage.argtypes = [POINTER(stream)]
#raw_buffer_encode = 

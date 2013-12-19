__all__ = ['FILTER_PREPACK', 'FILTER_DELTA', 'LZMACompressor',
           'LZMADecompressor']

import ctypes, io, struct
from ctypes import byref, POINTER
from . import _lzma

SIZE_T = struct.Struct('L')

def PyMemoryView_GET_BASE(buf):
    assert type(buf) is memoryview
    return ctypes.cast(SIZE_T.unpack(ctypes.string_at(id(buf)+SIZE_T.size*2,
                         SIZE_T.size))[0], POINTER(_lzma.uint8_t))

def ptr_diff(p1, p2):
    return ((ctypes.cast(p1, ctypes.c_void_p).value or 0) -
            (ctypes.cast(p2, ctypes.c_void_p).value or 0))


def _setup_filter(preset, **options):
    opts = _lzma.options_lzma()
    if _lzma.lzma_preset(byref(opts), preset):
        raise ValueError('Bad LZMA Preset {}'.format(preset))
    
    for opt,val in options.items():
        setattr(opts, opt, val)
        
    filters = (_lzma.filter*2)()
    filters[0].id = _lzma.FILTER_LZMA2
    filters[0].options = ctypes.addressof(opts)
    filters[1].id = _lzma.FILTER_UNKNOWN

    return POINTER(_lzma.filter)(filters), (opts,filters,)

FILTER_PREPACK = _setup_filter(9)
FILTER_DELTA = _setup_filter(6, mf=_lzma.MF_HC4, dict_size=512<<20)
FILTER_DELTA2 = _setup_filter(6, mf=_lzma.MF_HC4, dict_size=128<<20)

class _LZMACodec:
    # filter[1] is gc keepalive, only filter[0] is  used
    def __init__(self, *, bufsize=1048576, filter=FILTER_PREPACK):
        self.stream = _lzma.stream()
        self.stream.total_out = self.stream.total_in = 0
        self.stream.next_out = self.stream.next_in = None
        self.bufsize = bufsize
        self.eof = False
        err = self.initfunc(byref(self.stream), filter[0])

        if err:
            raise ValueError('raw_encoder returned errno', err)
        
    def code(self, data, action=_lzma.RUN):
        result = io.BytesIO()
        view = memoryview(data)
        self.stream.next_in = PyMemoryView_GET_BASE(view)
        self.stream.avail_in = len(view)

        err = 0
        buf = memoryview(bytearray(self.bufsize))
        buf_addr = PyMemoryView_GET_BASE(buf)
        while not err and ptr_diff(self.stream.next_out, buf_addr):
            self.stream.next_out = buf_addr
            self.stream.avail_out = self.bufsize
            err = _lzma.code(self.stream, action)

            if err > _lzma.STREAM_END:
                self.stream.next_out = self.stream.next_in = None
                raise ValueError('LZMA returned error code', err)

            result.write(buf[:ptr_diff(self.stream.next_out, buf_addr)])

        self.eof = err
        self.stream.next_out = self.stream.next_in = None
        return result.getvalue()

    def code_pump(self, read, write, callback, action=_lzma.RUN):
        cur = read()
        while cur:
            write(self.code(cur, action))
            callback()
            cur = read()

    def __del__(self):
        if self.stream is not None:
            _lzma.end(byref(self.stream))

class LZMACompressor(_LZMACodec):
    initfunc = _lzma.raw_encoder

    def compress(self, data):
        return self.code(data)

    def compress_pump(self, read, write, callback):
        self.code_pump(read, write, callback)

    def flush(self, mode=_lzma.FINISH):
        return self.code(b'', mode)

    def sync(self):
        return self.code(b'', _lzma.SYNC_FLUSH)

class LZMADecompressor(_LZMACodec):
    initfunc = _lzma.raw_decoder

    def decompress(self, data):
        # Fix empty decompress after EOS
        if not data:
            return ''
        return self.code(data)

    def decompress_pump(self, read, write, callback):
        self.code_pump(read, write, callback)

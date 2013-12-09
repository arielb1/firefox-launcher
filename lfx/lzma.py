__all__ = ['FILTER_PREPACK', 'FILTER_DELTA', 'LZMACompressor',
           'LZMADecompressor']

try:
    import lzma

    FILTER_PREPACK = {'id': lzma.FILTER_LZMA2,
                      'preset': 9
                      }

    # 512MiB mem filter (assuming profile is <256MiB)
    FILTER_DELTA = {'id': lzma.FILTER_LZMA2,
                    'preset': 9,
                    'dict_size': 512<<20
                    }

    def LZMACompressor(*, filter=FILTER_PREPACK):
        return lzma.LZMACompressor(format=lzma.FORMAT_RAW, filters=[filter])

    def LZMADecompressor(*, filter=FILTER_PREPACK):
        return lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[filter])
except ImportError:
    import ctypes
    from ._lzma import *


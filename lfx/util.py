import ssl, signal

__all__ = ['SANE_SSL_CONTEXT', 'di', 'ei']

SANE_SSL_CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
SANE_SSL_CONTEXT.verify_mode = ssl.CERT_REQUIRED
SANE_SSL_CONTEXT.set_default_verify_paths()

_have_sigint = False
_old_sigint_handler = None

def di():
    global _old_sigint_handler
    def _sigint_handler(signo, st):
        global _have_sigint
        _have_sigint = True
    _old_sigint_handler = signal.signal(signal.SIGINT, _sigint_handler)

def ei():
    global _old_sigint_handler, _have_sigint
    signal.signal(signal.SIGINT, _old_sigint_handler)
    _old_sigint_handler = None
    if _have_sigint:
        _have_sigint = False
        raise KeyboardInterrupt

import os

__all__ = ['gpg_verify']

def gpg_verify(signature, text, keychain):
    rT,wT = os.pipe()
    rS,wS = os.pipe()

    swpid = os.fork()
    if not swpid:
        os.close(rT)
        os.close(wT)
        os.close(rS)
        os.write(wS, signature)
        os._exit(1)
    os.close(wS)

    pid = os.fork()
    if not pid:
        os.close(wT)

        if rT == 3:
            os.dup2(rT,5)
            os.dup2(3,4)
            os.dup2(5,3)
        else:
            os.dup2(rS,3)
            os.dup2(rT,4)
        env = os.environ.copy()
        env['GNUPGHOME'] = keychain

        os.execvpe('gpg', ['gpg', '--verify', '/dev/fd/3', '/dev/fd/4'],
                   env)
        os._exit(1)

    os.close(rS)
    os.close(rT)
    os.write(wT, text)
    os.close(wT)
    
    _,status = os.waitpid(pid, 0)
    _ = os.waitpid(swpid, 0)
    return os.WIFEXITED(status) and not os.WEXITSTATUS(status)


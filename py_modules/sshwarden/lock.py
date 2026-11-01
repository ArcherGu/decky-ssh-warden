"""One system change at a time, across threads and processes.

Panel sections only disable their own controls and Decky runs every call in a thread. During an
update the old plugin process, the background uninstall (see cleanup.py) and up to two new
plugin processes can also overlap. flock() on a file in /run (writable by root only) serialises
all of them: each holder opens the file anew, so threads of one process exclude each other too,
and the kernel releases the lock when a holder is killed.
"""
import contextlib
import fcntl
import os

PATH = "/run/ssh-warden.lock"


@contextlib.contextmanager
def changes():
    fd = os.open(PATH, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # also releases the lock

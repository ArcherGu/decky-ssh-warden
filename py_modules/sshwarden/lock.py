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


@contextlib.contextmanager
def unless_busy():
    """Hold the lock shared, unless a change holds it right now; yields whether it is held.

    For reads that must not see a change halfway (see status.py), without making them wait.
    Shared, so reads at the same time (the panel's poll and a refresh, the command line) do
    not take each other for a change; a change waits for them to finish.
    """
    fd = os.open(PATH, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            held = True
        except BlockingIOError:
            held = False
        yield held
    finally:
        os.close(fd)

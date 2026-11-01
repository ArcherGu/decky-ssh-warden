"""Read and write files in directories the deck user controls, as root, without following symlinks.

The backend runs as root but keeps files under /home/deck (~/.ssh, Decky's settings directory).
Anything running as deck could replace a path component or the file itself with a symlink to,
say, /etc/shadow. So every step here works on directory file descriptors opened with
O_NOFOLLOW, never on plain paths, and only regular files are read.
"""
import os
import secrets
import stat

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def open_dir(path: str, create_mode: int | None = None) -> int:
    """File descriptor of the absolute directory `path`; no component may be a symlink.

    With `create_mode`, a missing last component is created with that mode.
    Raises FileNotFoundError if it does not exist, another OSError if it is unsafe.
    """
    parts = [p for p in path.split("/") if p]
    fd = os.open("/", _DIR_FLAGS)
    try:
        for i, part in enumerate(parts):
            try:
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if create_mode is None or i != len(parts) - 1:
                    raise
                os.mkdir(part, create_mode, dir_fd=fd)
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
    except BaseException:
        os.close(fd)
        raise
    return fd


def _read_regular(fd: int, limit: int) -> bytes:
    """Up to `limit` bytes of the open file `fd`, which must be a regular file. Closes `fd`."""
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError("not a regular file")
        data = f.read(limit + 1)
    if len(data) > limit:
        raise OSError("file too large")
    return data


def read(dir_fd: int, name: str, limit: int) -> bytes | None:
    """Contents of the regular file `name` in `dir_fd`, or None if it does not exist.

    Raises OSError if it is a symlink, a FIFO, a device, a directory or larger than `limit`.
    O_NONBLOCK keeps opening a FIFO from blocking forever.
    """
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    return _read_regular(fd, limit)


def write(dir_fd: int, name: str, data: bytes, mode: int, owner: tuple[int, int] | None = None) -> None:
    """Atomically replace `name` in `dir_fd` with `data`.

    The temporary file gets a random name and O_EXCL|O_NOFOLLOW, so nothing planted in the
    directory can redirect the write; mode and owner are set through the file descriptor.
    """
    tmp = f".{name}.{secrets.token_hex(8)}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fchmod(f.fileno(), mode)
            if owner:
                os.fchown(f.fileno(), *owner)
            os.fsync(f.fileno())
        # rename() replaces a symlink at `name` itself instead of following it.
        os.replace(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        try:
            os.unlink(tmp, dir_fd=dir_fd)
        except OSError:
            pass
        raise

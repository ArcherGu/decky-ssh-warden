"""Public keys in the deck user's ~/.ssh/authorized_keys: list, import from a file, remove."""
import base64
import binascii
import hashlib
import os
import pwd

from . import DECK_USER, safefile
from .errors import UserError

HOME = f"/home/{DECK_USER}"
SSH_DIR = f"{HOME}/.ssh"
MAX_IMPORT_BYTES = 64 * 1024
MAX_FILE_BYTES = 1024 * 1024

# Key types sshd accepts in authorized_keys (OpenSSH 10 dropped DSA).
KEY_TYPES = {
    "ssh-ed25519": "ED25519",
    "ssh-rsa": "RSA",
    "ecdsa-sha2-nistp256": "ECDSA",
    "ecdsa-sha2-nistp384": "ECDSA",
    "ecdsa-sha2-nistp521": "ECDSA",
    "sk-ssh-ed25519@openssh.com": "ED25519-SK",
    "sk-ecdsa-sha2-nistp256@openssh.com": "ECDSA-SK",
}


def parse_key(line: str) -> dict | None:
    """The public key on one authorized_keys line, or None for comments and invalid lines."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    # Options such as from="..." may come first, so look for a "<type> <base64>" pair anywhere.
    tokens = line.split()
    for i, key_type in enumerate(tokens[:-1]):
        if key_type not in KEY_TYPES:
            continue
        try:
            blob = base64.b64decode(tokens[i + 1], validate=True)
        except (binascii.Error, ValueError):
            continue
        # The blob starts with its own type name; it must agree with the text.
        name_len = int.from_bytes(blob[:4], "big")
        if blob[4:4 + name_len] != key_type.encode():
            continue
        digest = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
        return {
            "type": KEY_TYPES[key_type],
            "comment": " ".join(tokens[i + 2:]),
            "fingerprint": f"SHA256:{digest}",
        }
    return None


def _unsafe() -> UserError:
    return UserError(
        "keys_file_unsafe",
        "~/.ssh or ~/.ssh/authorized_keys is a symlink or not a regular file; edit it yourself",
    )


def _read_lines() -> list[str]:
    """Lines of authorized_keys, read without following symlinks (see safefile)."""
    try:
        dir_fd = safefile.open_dir(SSH_DIR)
    except FileNotFoundError:
        return []
    except OSError:
        raise _unsafe()
    try:
        data = safefile.read(dir_fd, "authorized_keys", MAX_FILE_BYTES)
    except OSError:
        raise _unsafe()
    finally:
        os.close(dir_fd)
    return data.decode("utf-8", "replace").splitlines() if data else []


def list_keys() -> list[dict]:
    """Keys in authorized_keys; none when the file is unsafe to read (the status must not fail)."""
    try:
        lines = _read_lines()
    except UserError:
        return []
    keys, seen = [], set()
    for line in lines:
        key = parse_key(line)
        if key and key["fingerprint"] not in seen:
            seen.add(key["fingerprint"])
            keys.append(key)
    return keys


def has_authorized_keys() -> bool:
    return bool(list_keys())


def _write_lines(lines: list[str]) -> None:
    """Replace authorized_keys atomically, owned by the deck user as sshd requires."""
    user = pwd.getpwnam(DECK_USER)
    owner = (user.pw_uid, user.pw_gid)
    home_fd = safefile.open_dir(HOME)
    try:
        try:
            os.mkdir(".ssh", 0o700, dir_fd=home_fd)
            created = True
        except FileExistsError:
            created = False
        dir_fd = os.open(".ssh", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
    except OSError:
        raise _unsafe()
    finally:
        os.close(home_fd)
    try:
        if created:  # made by us as root; sshd wants it to belong to the user
            os.fchown(dir_fd, *owner)
        data = "".join(f"{line}\n" for line in lines).encode()
        safefile.write(dir_fd, "authorized_keys", data, 0o600, owner)
    finally:
        os.close(dir_fd)


def import_file(path: str) -> dict:
    """Add every new public key found in `path` (a .pub file or an authorized_keys file)."""
    name = os.path.basename(path)
    try:
        data = safefile.read_path(path, MAX_IMPORT_BYTES)
    except OSError as e:
        reason = e.strerror or str(e)
        raise UserError("key_file_unreadable", "Cannot read {file}: {reason}", file=name, reason=reason)
    # Never parse, store or echo a private key that was picked by mistake.
    if b"PRIVATE KEY" in data or b"PuTTY-User-Key-File" in data:
        raise UserError("key_file_private", "{file} is a private key; pick the matching .pub file", file=name)

    lines = _read_lines()
    known = {k["fingerprint"] for k in list_keys()}
    found, added = 0, []
    for line in data.decode("utf-8", "replace").splitlines():
        key = parse_key(line)
        if not key:
            continue
        found += 1
        if key["fingerprint"] not in known:
            known.add(key["fingerprint"])
            added.append(line.strip())
    if not found:
        raise UserError("key_file_invalid", "{file} contains no SSH public key", file=name)
    if added:
        _write_lines(lines + added)
    return {"added": len(added), "skipped": found - len(added)}


def remove_key(fingerprint: str) -> None:
    """Remove every line holding the key with this fingerprint.

    Without password login the last key is the only way in, so it cannot be removed.
    """
    from .sshd import password_auth_enabled  # imported here because sshd imports this module

    lines = _read_lines()
    kept = [line for line in lines if (parse_key(line) or {}).get("fingerprint") != fingerprint]
    if len(kept) == len(lines):
        raise UserError("key_not_found", "No public key with fingerprint {fingerprint}", fingerprint=fingerprint)
    if not any(parse_key(line) for line in kept) and not password_auth_enabled():
        raise UserError(
            "last_key",
            "This is the last public key and password login is off; removing it would lock everyone out",
        )
    _write_lines(kept)

"""Public keys in the deck user's ~/.ssh/authorized_keys: list, import from a file, remove."""
import base64
import binascii
import hashlib
import os
import pwd

from . import DECK_USER
from .errors import UserError

SSH_DIR = f"/home/{DECK_USER}/.ssh"
AUTHORIZED_KEYS = f"{SSH_DIR}/authorized_keys"
MAX_IMPORT_BYTES = 64 * 1024

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


def _read_lines() -> list[str]:
    try:
        with open(AUTHORIZED_KEYS, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return []


def list_keys() -> list[dict]:
    keys, seen = [], set()
    for line in _read_lines():
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
    if not os.path.isdir(SSH_DIR):
        os.mkdir(SSH_DIR, 0o700)
        os.chown(SSH_DIR, user.pw_uid, user.pw_gid)
    tmp = f"{AUTHORIZED_KEYS}.ssh-warden.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("".join(f"{line}\n" for line in lines))
    os.chmod(tmp, 0o600)
    os.chown(tmp, user.pw_uid, user.pw_gid)
    os.replace(tmp, AUTHORIZED_KEYS)


def import_file(path: str) -> dict:
    """Add every new public key found in `path` (a .pub file or an authorized_keys file)."""
    name = os.path.basename(path)
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_IMPORT_BYTES + 1)
    except OSError as e:
        raise UserError("key_file_unreadable", "Cannot read {file}: {reason}", file=name, reason=e.strerror)
    # Never parse, store or echo a private key that was picked by mistake.
    if b"PRIVATE KEY" in data or b"PuTTY-User-Key-File" in data:
        raise UserError("key_file_private", "{file} is a private key; pick the matching .pub file", file=name)
    if len(data) > MAX_IMPORT_BYTES:
        raise UserError("key_file_invalid", "{file} contains no SSH public key", file=name)

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

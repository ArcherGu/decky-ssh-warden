import asyncio

import decky

from sshwarden import account, cleanup, keys, lock, port, settings, sshd, status, trust
from sshwarden.errors import UserError


def _exclusive(fn, *args):
    # Changes run one at a time (see lock.py): otherwise two could overwrite each other's
    # settings.json (losing firewall records) or both pass checks meant to be exclusive
    # (last key vs. password login).
    with lock.changes():
        return fn(*args)


async def _call(fn, *args, exclusive: bool = True) -> dict:
    """Run a blocking backend function off the event loop; report errors to the UI as data.

    Only reads, and functions that take lock.changes() themselves, may pass exclusive=False.
    """
    try:
        if exclusive:
            data = await asyncio.to_thread(_exclusive, fn, *args)
        else:
            data = await asyncio.to_thread(fn, *args)
        return {"ok": True, "data": data}
    except Exception as e:
        decky.logger.exception("%s failed", getattr(fn, "__name__", fn))
        result = {"ok": False, "error": str(e)}
        if isinstance(e, UserError):
            # The panel shows these in the user's language.
            result.update(code=e.code, params=e.params)
        return result


class Plugin:
    async def get_status(self) -> dict:
        return await _call(status.collect, exclusive=False)

    async def set_running(self, on: bool) -> dict:
        return await _call(sshd.set_running, bool(on))

    async def set_autostart(self, on: bool) -> dict:
        return await _call(sshd.set_autostart, bool(on))

    async def set_autooff(self, minutes: int) -> dict:
        """Stop sshd after `minutes`; 0 cancels a pending auto-off."""
        if int(minutes) <= 0:
            return await _call(sshd.cancel_autooff)
        return await _call(sshd.schedule_autooff, int(minutes))

    async def set_port(self, number: int) -> dict:
        return await _call(port.set_port, int(number))

    async def set_password_auth(self, on: bool) -> dict:
        return await _call(sshd.set_password_auth, bool(on))

    async def change_password(self, current_password: str, new_password: str) -> dict:
        return await _call(account.change_password, str(current_password), str(new_password))

    async def import_keys(self, path: str) -> dict:
        return await _call(keys.import_file, str(path))

    async def remove_key(self, fingerprint: str) -> dict:
        return await _call(keys.remove_key, str(fingerprint))

    async def set_trusted_mode(self, on: bool) -> dict:
        return await _call(trust.set_enabled, bool(on))

    async def set_network_trusted(self, uuid: str, on: bool) -> dict:
        return await _call(trust.set_network_trusted, str(uuid), bool(on))

    async def repair_firewall(self) -> dict:
        return await _call(trust.repair_firewall)

    async def _main(self):
        settings.init(decky.DECKY_PLUGIN_SETTINGS_DIR)
        decky.logger.info("SSH Warden loaded")
        restored = await _call(cleanup.restore_after_update, exclusive=False)
        if restored.get("data"):
            decky.logger.info("Settings put back after an update: %s", restored["data"])

    async def _unload(self):
        decky.logger.info("SSH Warden unloaded")

    async def _uninstall(self):
        # Leave no orphaned firewall zone/rules or sshd drop-in behind. Decky also calls this
        # before an update; the new version then puts the settings back. It kills this process
        # within 5 s, so the work runs in a background service (see cleanup.py).
        # Not behind the change lock: a change still running must not use up those 5 s.
        result = await _call(cleanup.start_uninstall, decky.DECKY_PLUGIN_SETTINGS_DIR, exclusive=False)
        if not result["ok"]:
            # Best effort if the service could not start (uninstall() takes the lock itself).
            result = await _call(cleanup.uninstall, exclusive=False)
        decky.logger.info("SSH Warden uninstall: %s", result)

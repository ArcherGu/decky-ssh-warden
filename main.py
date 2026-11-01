import asyncio

import decky

from sshwarden import account, cleanup, keys, port, settings, sshd, status, trust
from sshwarden.errors import UserError


async def _call(fn, *args) -> dict:
    """Run a blocking backend function off the event loop; report errors to the UI as data."""
    try:
        return {"ok": True, "data": await asyncio.to_thread(fn, *args)}
    except Exception as e:
        decky.logger.exception("%s failed", getattr(fn, "__name__", fn))
        result = {"ok": False, "error": str(e)}
        if isinstance(e, UserError):
            # The panel shows these in the user's language.
            result.update(code=e.code, params=e.params)
        return result


class Plugin:
    async def get_status(self) -> dict:
        return await _call(status.collect)

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

    async def change_password(self, new_password: str) -> dict:
        return await _call(account.change_password, str(new_password))

    async def import_keys(self, path: str) -> dict:
        return await _call(keys.import_file, str(path))

    async def remove_key(self, fingerprint: str) -> dict:
        return await _call(keys.remove_key, str(fingerprint))

    async def set_trusted_mode(self, on: bool) -> dict:
        return await _call(trust.set_enabled, bool(on))

    async def set_network_trusted(self, uuid: str, on: bool) -> dict:
        return await _call(trust.set_network_trusted, str(uuid), bool(on))

    async def _main(self):
        settings.init(decky.DECKY_PLUGIN_SETTINGS_DIR)
        decky.logger.info("SSH Warden loaded")

    async def _unload(self):
        decky.logger.info("SSH Warden unloaded")

    async def _uninstall(self):
        # Leave no orphaned firewall zone/rules or sshd drop-in behind.
        result = await _call(cleanup.revert_all)
        decky.logger.info("SSH Warden uninstalled, cleanup: %s", result)

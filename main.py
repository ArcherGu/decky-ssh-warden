import asyncio

import decky

from sshwarden import status


async def _call(fn, *args) -> dict:
    """Run a blocking backend function off the event loop; report errors to the UI as data."""
    try:
        return {"ok": True, "data": await asyncio.to_thread(fn, *args)}
    except Exception as e:
        decky.logger.exception("%s failed", getattr(fn, "__name__", fn))
        return {"ok": False, "error": str(e)}


class Plugin:
    async def get_status(self) -> dict:
        return await _call(status.collect)

    async def _main(self):
        decky.logger.info("SSH Warden loaded")

    async def _unload(self):
        decky.logger.info("SSH Warden unloaded")

    async def _uninstall(self):
        decky.logger.info("SSH Warden uninstalled")

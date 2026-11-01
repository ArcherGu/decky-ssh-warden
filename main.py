import decky


class Plugin:
    async def _main(self):
        decky.logger.info("SSH Warden loaded")

    async def _unload(self):
        decky.logger.info("SSH Warden unloaded")

    async def _uninstall(self):
        decky.logger.info("SSH Warden uninstalled")

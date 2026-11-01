# SSH Warden

**English** | [简体中文](README.zh-CN.md)

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for managing SSH on the Steam Deck from Game Mode. Turn SSH on or off, change its port, manage password login and keep SSH open only on networks you trust, all without switching to Desktop Mode or typing commands.

## Features

| Section | What you can do |
| --- | --- |
| SSH service | Turn SSH on or off; start it at boot; stop it automatically after 15 min / 30 min / 1 h / 2 h |
| Status | Current network with a ready-to-use connection command, whether SSH is reachable on it, active sessions, failed login attempts in the last 24 hours, most recent login |
| Connection | Change the SSH port |
| Login security | Allow or disallow password login; change the `deck` user's password |
| Trusted networks | Keep SSH open only on the networks you tick; every other network (e.g. public Wi-Fi) is blocked by the firewall |

## Safety by design

- **Changing settings cannot lock you out.** The plugin only writes its own sshd drop-in, `/etc/ssh/sshd_config.d/05-ssh-warden.conf`, and never touches the main config. Every change is validated with `sshd -t`, and sshd must come back listening on the expected port; if any step fails, the previous configuration is restored automatically.
- **No password-login switch-off without keys.** While `~/.ssh/authorized_keys` has no keys, the backend refuses to disable password login and the toggle is disabled.
- **Passwords are never logged.** The new password is passed to `chpasswd` on stdin, so it never appears in process arguments or logs.
- **Invisible on public networks.** With "SSH only on trusted networks" on, trusted networks are moved to a dedicated firewall zone, `sshwarden` (a copy of the default zone, so streaming and other features keep working). All other networks drop the SSH port, so a port scan shows nothing there.
- **Every firewall rule is accounted for.** Each rule the plugin adds is recorded in `~/homebrew/settings/decky-ssh-warden/settings.json`. When the port or mode changes, new rules are added before old ones are removed, so there is no gap and nothing is left behind.
- **Uninstalling restores the system.** Removing the plugin turns trusted mode off, deletes every firewall rule and the sshd drop-in it created, and cancels a pending auto-off. SSH returns to the system defaults (port 22, password login allowed).
- **Polling only while the panel is open.** Closing the Quick Access Menu stops all background work.

The plugin runs as `root` (`flags: ["root"]` in `plugin.json`), because managing sshd, changing passwords and configuring the firewall all require it.

## Known limitations

- Only two sshd settings are managed: the port and password login. Finer options such as `AllowUsers` are not handled.
- Public keys are only counted. To add or remove keys, edit `~/.ssh/authorized_keys` in Desktop Mode.
- Auto-off uses a transient systemd timer, so it does not survive a reboot of the Deck.

## Installation

Build and package on your computer:

```bash
pnpm install
pnpm package      # produces out/decky-ssh-warden.zip
```

Then install it either way:

- On the Deck, enable Developer Mode in Decky's Settings → Developer, then use "Install Plugin from ZIP" and pick `out/decky-ssh-warden.zip`.
- Or deploy over SSH in one step (sudo will ask for the deck user's password):

  ```bash
  scripts/deploy.sh deck@<deck-ip>
  ```

## Development

```bash
pnpm build        # outputs dist/index.js
pnpm typecheck
```

- Frontend: `src/` (React + `@decky/ui`), one file per panel section in `src/sections/`.
- Backend: `main.py` only forwards calls; the logic lives in `py_modules/sshwarden/`. You can test it on the Deck without the UI:

  ```bash
  cd ~/homebrew/plugins/decky-ssh-warden/py_modules
  sudo python3 -B -m sshwarden status
  sudo python3 -B -m sshwarden port 2222
  ```

### Safety net for remote testing: `dev/deck-guard`

When you test SSH-related features remotely, one mistake can leave the Deck unreachable. `dev/deck-guard` is a development-time watchdog:

- On install it takes a "known good" snapshot of sshd, the `deck` password, firewalld and NetworkManager zones.
- A systemd timer checks every minute. If the state differs from the snapshot **and** `~/.ssh-warden-dev/heartbeat` has not been touched for 5 minutes (meaning the developer can no longer get in), it restores the snapshot.
- While developing, touch the heartbeat file before every command you run over SSH.

```bash
# On the Deck, as root
sudo bash dev/deck-guard/install.sh             # install and take the snapshot
sudo /var/lib/ssh-warden-dev/guard.sh status    # show its state
sudo bash dev/deck-guard/uninstall.sh           # remove it when done (also deletes the stored password hash copy)
```

> The guard restores all SSH-related settings after 5 minutes without a heartbeat. **Do not keep it installed for normal use**, or the settings you change in the plugin will be reverted.

`dev/cdp.py` runs JavaScript, clicks toggles and takes screenshots on the Deck through Steam's remote debugging port, for checking the UI.

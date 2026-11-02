# AGENTS.md

Guidance for AI agents working on this project. User-facing documentation lives in [README.md](README.md) (English) and [README.zh-CN.md](README.zh-CN.md) (Simplified Chinese); this file covers the conventions, pitfalls and testing workflow you need while developing.

## Project at a glance

SSH Warden is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that manages sshd from the Quick Access Menu in the Steam Deck's Game Mode: on/off, start at boot, auto-off timer, port, password login, password change, public keys, and "SSH only on trusted networks".

- The plugin runs as **root** (`flags: ["root"]` in `plugin.json`). A backend bug can break the system directly or lock the user out of SSH.
- Target: SteamOS 3.9, Decky Loader 3.3.x. The backend runs inside Decky's bundled Python 3.14 (a PyInstaller build).
- Development machine: macOS with Node 24 and pnpm 12. A stock macOS `python3` (3.9) **cannot import the backend modules** (they use 3.10+ syntax such as `str | None`), so the backend can only be run and tested on the Deck.
- The panel is in **English and Simplified Chinese**, following Steam's language (`src/i18n.ts`). Code comments, commit messages, logs and the backend's own messages are in English.

## Repository layout

| Path | Purpose |
| --- | --- |
| `main.py` | Decky backend entry point. It only forwards: every method is `return await _call(fn, *args)` |
| `py_modules/sshwarden/proc.py` | The only place that runs system commands: `run()`, `succeeds()`, `split_terse()` |
| `py_modules/sshwarden/safefile.py` | Reading and writing files under `/home/deck` as root without following symlinks |
| `py_modules/sshwarden/lock.py` | `changes()`: the cross-process lock every system change holds |
| `py_modules/sshwarden/errors.py` | `UserError`: an error for the user, with a code the panel translates |
| `py_modules/sshwarden/sshd.py` | sshd service state, on/off, auto-off timer, config read/write (drop-in + validation + rollback), login history |
| `py_modules/sshwarden/net.py` | NetworkManager connections, firewalld zones and rules, `sync_ssh_firewall()`, `zones_snapshot()` |
| `py_modules/sshwarden/port.py` | The full port-change flow (firewall → sshd → cleanup) |
| `py_modules/sshwarden/trust.py` | Trusted-networks mode |
| `py_modules/sshwarden/account.py` | Password change (needs the current password once one is set) |
| `py_modules/sshwarden/keys.py` | `~/.ssh/authorized_keys`: parse keys and fingerprints, import from a file, remove |
| `py_modules/sshwarden/status.py` | Status summary polled by the frontend |
| `py_modules/sshwarden/cleanup.py` | Undoes every system change the plugin made (on uninstall) and puts the user's settings back after an update |
| `py_modules/sshwarden/settings.py` | `~/homebrew/settings/decky-ssh-warden/settings.json` |
| `py_modules/sshwarden/__main__.py` | Command-line entry for testing the backend on the Deck without the UI |
| `src/api.ts` | `callable` wrappers for backend methods and the `Status` type |
| `src/i18n.ts` | Every UI string in both languages, backend error translations, language detection |
| `src/sections/*.tsx` | One file per panel section |
| `src/components/*.tsx` | Dialogs |
| `src/useStatus.ts` / `src/useAction.ts` | Poll the status every 3 seconds / run an action, toast errors, then refresh |
| `scripts/package.sh` / `scripts/deploy.sh` | Build a zip Decky can install / deploy over SSH |
| `dev/deck-guard/` | SSH auto-recovery watchdog for remote testing (see below; **critical**) |
| `dev/cdp.py` | Runs JS, clicks toggles and takes screenshots through Steam's CEF debugging port |

## Backend conventions

- **Run system commands only through `proc.run()`**, never `subprocess` directly. Decky is a PyInstaller app that points `LD_LIBRARY_PATH` at its bundled libraries, which makes system programs such as `sshd`, `bash` and `nmcli` fail to start; `run()` cleans that up. It also pins `LC_ALL=C` and `PATH` so output stays parseable. Input is encoded strictly (it may be a password, which must reach the command exactly; an unencodable string raises), output is decoded leniently, and a failed command's `CommandError` keeps its `returncode`.
- Backend functions are synchronous. `_call()` in `main.py` runs them with `asyncio.to_thread` and returns `{"ok": true, "data": ...}` or `{"ok": false, "error": "..."}`. For errors the user should see, `raise UserError("<code>", "<English message with {params}>", **params)`; `_call()` adds `code` and `params` to the result and the panel shows the translation of that code from `errors` in `src/i18n.ts`, falling back to the English message. `CommandError`, raised by `proc.run()`, is a `UserError` with the code `command_failed`.
- **Every change holds `lock.changes()`**, an `flock` on `/run/ssh-warden.lock`. `_call()` takes it unless `exclusive=False` (only for reads and for functions that take it themselves; taking it twice in one process deadlocks), and the CLI takes it for its change commands. Panel sections only disable their own controls, and during an update the old plugin, the background uninstall and two new plugin processes overlap, so without it changes would race on `settings.json` and on checks that must be atomic.
- **The system is the source of truth**, not `settings.json`. Settings only store two kinds of data: changes the plugin made (so they can be undone) and user preferences (the trusted-network list).
- Known parsing pitfalls:
  - `sshd -T` prints keys in mixed case (e.g. `PasswordAuthentication yes`); `effective_config()` lower-cases them.
  - `nmcli -t` escapes `:` and `\`; always split with `split_terse()` (network names can contain non-ASCII text and colons).

### sshd configuration

- **Only edit the plugin's own drop-in**, `/etc/ssh/sshd_config.d/05-ssh-warden.conf`. Never edit `/etc/ssh/sshd_config`. The main config `Include`s the drop-in directory on its second line, and for most options sshd keeps the first value it reads, so the `05-` prefix wins over SteamOS's own `20-` and `99-` files. **`Port` is an exception: every `Port` line adds a listening port.** No other file on SteamOS sets `Port` today; if one did, sshd would listen on both ports (which `sshd.ports()` already reports).
- Managed keys are listed in `sshd.MANAGED_KEYS`. To manage a new sshd option, add it there and change it through `sshd.update_config()`. That function runs `sshd -t`, restarts sshd and checks it is listening on the expected port; if any step fails it restores the previous file and restarts sshd. Do not bypass it.
- To return an option to the system default, pass `None` to drop it (e.g. port back to 22) instead of writing the default value.

### Firewall (firewalld)

- SteamOS defaults: default zone `public`, allowing the `ssh` service and TCP/UDP ports `1024-65535`. `firewall-cmd --query-port` also matches port ranges.
- **Every rule the plugin adds must go through `net.sync_ssh_firewall()`.** It computes the wanted rules for the current mode, adds new rules before removing old ones (so SSH is never blocked in between), and records what it added in the `firewall` field of `settings.json` so it can be undone. Do not call `firewall-cmd --add-*` anywhere else.
- Trusted networks use a zone of our own, `sshwarden` (`net.TRUSTED_ZONE`): a copy of the default zone's services and ports (excluding ports the plugin opened itself); trusted connections get `connection.zone=sshwarden`. Every other network's zone **drops** the SSH port (drop, not reject), so on a public network the port looks like nothing is there.
- Every rule is applied to both the runtime and the permanent configuration (`net._firewall()` does this).
- A rule is recorded before it is added, so a plugin killed halfway can leave a record whose rule is missing. Switching trusted mode off saves `trusted_mode=False` before changing anything, so an interrupted switch-off leaves the zone or its rules behind while the mode already reads off. `net.out_of_sync()` finds both (missing records; the zone or its rules while off; no zone while on), `status.collect()` reports them as `firewall_out_of_sync` (from the snapshot it already reads, and only while no change holds the lock: `lock.unless_busy()`), and the panel offers `trust.repair_firewall()`, which re-applies the saved mode. **The panel's `trusted_mode` is that saved mode**, so the frontend's "will the repair block the current network?" check and the backend's repair always agree; do not derive it from the system again.
- After `firewall-cmd --reload`, use the logic in `net.reload_firewall()`: rebind **only** Wi-Fi and Ethernet devices to their zones. Leave every other interface alone, e.g. VPN/proxy tun devices created by other plugins; they may not belong to any zone, and binding them would change the user's network setup.
- Each `firewall-cmd` call costs about 0.3 s on the Deck. `status.collect()` runs every 3 seconds while the panel is open, so **the status must read all zones at once with `zones_snapshot()`**; do not add per-zone `firewall-cmd` calls there. A status call currently takes about 0.7 s.

### Safety invariants (new code must keep these)

- **Assume any local process can call the plugin's methods.** Decky serves its auth token at `/auth/token` without authentication, and `/ws` accepts any client that presents it. So a method must never let a program running as deck gain root: that is why changing the password needs the current one (`account.change_password()` checks it with `unix_chkpwd`, as `passwd` would).
- Never lock the user out: disabling password login requires keys that sshd actually accepts (`sshd.accepts_keys()`: PubkeyAuthentication, AuthorizedKeysFile, AuthenticationMethods); a failed port change rolls back; any action that could cut off the network the user is on needs a confirmation dialog in the frontend.
- Passwords go to `chpasswd` on stdin only. They must never appear in command arguments, logs or return values.
- Disabling password login needs at least one key, and removing the last key needs password login on. `keys.remove_key()` checks the second rule itself (it imports `sshd` inside the function because `sshd` imports `keys`).
- Never read a private key into anything that is stored, logged or returned: `keys.import_file()` rejects files that look like one before parsing them.
- **Never open a path the caller chose as root.** `keys.import_file()` reads the picked file as the deck user (`runuser -u deck -- timeout 4 head -c ...`); otherwise any local process could probe root-only files through the plugin. Keep a timeout *inside* `runuser`: it forks, so killing it on `run()`'s timeout would leave `head` blocked on a FIFO for good. Limits on what a command printed count bytes (`len(text.encode())`), not characters.
- **Never touch a path under `/home/deck` with plain `open()`, `chmod()` or `chown()`.** Those directories belong to deck, and anything running as deck could swap in a symlink to `/etc/shadow`. Use `safefile` (directory descriptors, `O_NOFOLLOW`, a random temporary name with `O_EXCL`, `fchmod`/`fchown`, only regular files read). Files the plugin creates there for the user, such as `~/.ssh` and `authorized_keys`, must belong to deck.
- **Whenever you add a new kind of system change, extend `cleanup.revert_all()`** so uninstalling the plugin leaves nothing behind. Decky also runs `_uninstall` before every update or reinstall (`browser._install()` → `uninstall_plugin()`), so if the user would want the setting back after an update, note it in `cleanup._note_settings()` and re-apply it in `cleanup._restore()` (idempotently: Decky starts a new plugin twice and kills the first process within seconds, so a restore may run again).
- **Decky SIGKILLs a plugin 5 s after asking it to stop**, then deletes its directory. `_uninstall` therefore only calls `cleanup.start_uninstall()`, which copies the package to `/run/ssh-warden-uninstall` and runs `python3 -m sshwarden uninstall` from there as the transient service `ssh-warden-uninstall`. Keep `_uninstall` itself well under 5 s.

## Frontend conventions

- One component per section in `src/sections/`, taking `status` and `refresh` props. Run actions through `useAction(refresh)`, which handles the busy state, error toasts and refreshing.
- Wrap new backend methods in `src/api.ts` with `callable` plus `unwrap`, and keep the `Status` type in sync with what `status.collect()` returns.
- **In the current Steam client, `ConfirmModal` does not close itself after OK or Cancel**: always call `closeModal()` in `onOK` and `onCancel`. Use `components/ConfirmDialog.tsx` for simple yes/no dialogs.
- The Quick Access Menu is only about 300 px wide: use `layout="below"` for dropdowns and other controls that may show long text, or it gets truncated.
- **Never hard-code UI text.** Add each string to both `en` and `zhCN` in `src/i18n.ts` and use it through `t` (`zhCN` is typed as `typeof en`, so a missing translation fails the typecheck). Strings that contain values are functions, so each language can order the words its own way.
- The language is read once, when the plugin loads: `LocalizationManager.m_rgLocalesToUse[0]` is Steam's UI language (e.g. `zh-cn`, `en-us`), with `navigator.language` as a fallback. Simplified Chinese (`zh-cn`, `zh-hans`) gets Chinese; every other language gets English. Steam restarts when its language changes, which reloads the plugin.
- Import `toaster` from `@decky/api`, not `@decky/ui`.
- Closing the Quick Access Menu unmounts the plugin UI and stops polling. Do not add background timers.

## Build and checks

```bash
pnpm install
pnpm typecheck    # tsc on src, then on the frontend tests (tsconfig.test.json)
pnpm build        # rollup → dist/index.js
pnpm package      # build and package out/decky-ssh-warden.zip
pnpm test         # frontend (node --test) and backend (unittest) tests
pnpm check:i18n   # every UserError code the backend raises is translated in both languages
```

- **CI** (`.github/workflows/ci.yml`) runs on every push and pull request: frozen install, typecheck, frontend tests and `pnpm package`, whose zip is kept as the run's artifact for 14 days; backend tests and `check:i18n` on Python 3.14 (what Decky bundles); `bash -n` on the shell scripts. Keep it green.
- The backend needs Python 3.10+. A stock macOS `python3` is 3.9, so point the scripts at a newer one: `PYTHON=/opt/homebrew/bin/python3.12 pnpm test`.
- **Add tests with every change to backend logic.** `tests/backend/helpers.py` has `TempDirTest` (a real temporary directory, settings.json and lock file per test) and `FakeNetwork`, a fake firewalld + NetworkManager for `net.py`/`trust.py`; patch `run`/`succeeds` in the module under test rather than running system commands. Tests run unprivileged, so they cannot touch the system. `test_main.py` imports `main.py` with a stand-in `decky` module and checks every method `src/api.ts` calls exists on `Plugin`; `test_syntax.py` compiles every `.py` file in the repository, including `dev/cdp.py`. A few tests need Linux tools (GNU `timeout`) and are skipped on macOS; CI runs them. Frontend tests live in `tests/frontend/*.test.ts` and import `src/` files with their `.ts` extension; Node runs them by stripping the types, so only erasable TypeScript syntax works there (`tsconfig.test.json` enforces it with `erasableSyntaxOnly`).

- pnpm 12 no longer reads a `pnpm` field in `package.json`; those settings live in `pnpm-workspace.yaml`.
- `tsconfig.json` needs `skipLibCheck`: the `@decky/api` type declarations reference `react-router`, which is not installed. It also sets `"types": []`, so `@types/node` (for the tests) does not let `src` use Node globals such as `process`, which do not exist in Steam; `tsconfig.test.json` adds `node` back.
- Inside Claude Code's macOS sandbox, `gh`, `git push` and `pnpm install` may fail with `x509: OSStatus -26276` or keychain errors, and `mktemp` (used by `scripts/package.sh`) may fail with "Operation not permitted". These are sandbox restrictions, not broken credentials or scripts.

## Testing on the Deck

Ask the user for the Deck's address and login credentials. **Never write them into any file in the repository**; helper scripts that contain a password belong in the session's temporary directory and must be deleted afterwards.

### Rule one: install the watchdog first

Before any test that could affect SSH access (stopping sshd, changing the port or password, changing public keys, the firewall or network zones), **install `dev/deck-guard` on the Deck**. The user is often away from the screen; if the Deck becomes unreachable, nobody can rescue it.

- `install.sh` takes a "known good" snapshot of sshd, the deck user's password hash, firewalld, NetworkManager zones and `~/.ssh/authorized_keys` (only when the current state is healthy), then enables a systemd timer that runs every minute.
- If the state differs from the snapshot **and** `~/.ssh-warden-dev/heartbeat` has not been touched for 5 minutes, the watchdog restores the snapshot.
- **Touch `~/.ssh-warden-dev/heartbeat` at the start of every SSH command**, or the watchdog may restore the snapshot in the middle of a test.
- After installing, run a deliberate break test to prove it works: first arm an independent fallback with `systemd-run --on-active=8min`, then schedule the breakage with `systemd-run` (so it does not depend on your SSH session), and poll from the development machine until SSH comes back.
- The watchdog covers sshd, the password, firewalld, NetworkManager zones and `~/.ssh/authorized_keys`. If a new feature changes system state it does not cover, **extend the fingerprint and restore logic in `guard.sh` before testing that feature**.
- When you are done, **you must uninstall it**: `sudo bash dev/deck-guard/uninstall.sh`. Otherwise every setting the user changes in the plugin is reverted after 5 minutes. The uninstall script also deletes the copy of the password hash in the snapshot. Uninstall last, after the test cleanup, and stop touching the heartbeat file afterwards (or remove `~/.ssh-warden-dev` again), since touching it recreates the directory.

### Testing tips

- Backend CLI on the Deck (always pass `-B`, otherwise root-owned `__pycache__` directories cannot be removed later by a normal user):

  ```bash
  cd ~/homebrew/plugins/decky-ssh-warden/py_modules
  sudo python3 -B -m sshwarden status
  sudo python3 -B -m sshwarden service on|off
  sudo python3 -B -m sshwarden autostart on|off
  sudo python3 -B -m sshwarden autooff 30|cancel
  sudo python3 -B -m sshwarden port 2222
  sudo python3 -B -m sshwarden password-auth on|off
  printf '%s\n%s\n' '<current password>' '<new password>' | sudo python3 -B -m sshwarden passwd
  sudo python3 -B -m sshwarden trusted-mode on|off
  sudo python3 -B -m sshwarden trust <connection UUID> on|off
  sudo python3 -B -m sshwarden repair-firewall   # make the firewall match the saved mode again
  sudo python3 -B -m sshwarden keys
  sudo python3 -B -m sshwarden key-import /path/to/key.pub
  sudo python3 -B -m sshwarden key-remove SHA256:<fingerprint>
  sudo python3 -B -m sshwarden cleanup      # revert everything
  sudo python3 -B -m sshwarden uninstall    # note the settings, then revert (what _uninstall runs)
  ```

- **Established SSH sessions survive sshd stops, restarts and firewall changes.** Do "stop → check → start again" tests inside a single SSH session.
- After changing the port, connect on the new port. To undo a password change, write back the **original hash** with `usermod -p "$(cat /var/lib/ssh-warden-dev/baseline/shadow-hash)" deck`; setting the old password again produces a different salt, so the hash would not match the snapshot.
- To test disabling password login or the key section, generate throwaway key pairs on the development machine and add them with `key-import` or `ssh-copy-id`; remove them afterwards, together with `~/.ssh` if the Deck did not have one before. With password login off, log in with the throwaway key (`ssh -i ... -o IdentitiesOnly=yes`); `sudo` still takes the password.
- To test the file picker, put the test `.pub` file directly in `/home/deck` (the picker's start folder) so it is in the first listing.
- At the end of every test, check `sudo /var/lib/ssh-warden-dev/guard.sh status` reports `changed components: ''`, i.e. the system is fully back to the snapshot.
- Switching trusted mode takes a few seconds (about 6.5 s on, 4.5 s off) and the toggles are disabled meanwhile. In UI tests, wait for an operation to finish before clicking the next toggle.

### Deploying

- Use `scripts/deploy.sh` for normal deployments.
- Hot reload during development: Decky **only hot-reloads plugins that have the `debug` flag**. Add `debug` only to the `plugin.json` deployed on the Deck; never commit it. The first time a new plugin directory appears, `plugin_loader` must be restarted once.
- **Do not `systemctl restart plugin_loader` while a hot reload may be in progress.** The service uses `KillMode=process`; if the old instance hangs while reloading a plugin, the restart leaves an orphaned Decky process running alongside the new one. The safe sequence is: `systemctl stop plugin_loader` → check for leftover `Decky Loader`, `/services/PluginLoader` or `plugins/*/main.py)` processes and clean them up → replace the files → `systemctl start plugin_loader`. Helper processes started by other plugins may also survive a restart; that is their own behaviour, so leave them alone.
- `/tmp` on the Deck is shared: delete only files you created, by explicit name, never with wildcards.
- If downloads from the Deck are slow or blocked, download on the development machine, verify the SHA256, then copy the file over.

### Checking the UI (`dev/cdp.py`)

Run it on the Deck as the deck user. Steam's debugging port is `127.0.0.1:8080` (enabled by Decky).

```bash
python3 cdp.py targets
python3 cdp.py eval SharedJSContext 'DFL.Navigation.OpenQuickAccessMenu(DFL.QuickAccessTab.Decky)'
python3 cdp.py eval SharedJSContext 'DeckyPluginLoader.deckyState.setActivePlugin("SSH Warden")'
python3 cdp.py shot QuickAccess /tmp/qam.png
python3 cdp.py toggle QuickAccess '启用 SSH'   # labels are in the Deck's current language
python3 cdp.py eval SharedJSContext 'DFL.Navigation.CloseSideMenus()'
```

- Dropdown menus and dialogs render in the Big Picture target, not in `QuickAccess`; its title follows Steam's language (`Steam Big Picture Mode`, `Steam 大屏幕模式`, ...). After interacting with a dialog, the Quick Access Menu usually closes; reopen it before taking a screenshot (hidden windows do not render and screenshots time out).
- To change a controlled input, set the value through the `value` setter on `HTMLInputElement.prototype` and dispatch an `input` event so React notices. Password fields are plain `input` elements too, not `type=password`, and the Big Picture page also contains many `type=file` inputs, so select `input:not([type=file])` inside the dialog.
- To check the other language without changing Steam's (which restarts Steam), reload only this plugin's frontend with a different locale list and put Steam's back right away. Run it again with Steam's own locale to switch back:

  ```js
  (async () => {
    const lm = LocalizationManager, saved = lm.m_rgLocalesToUse;
    const p = DeckyPluginLoader.plugins.find((p) => p.name === "SSH Warden");
    try {
      lm.m_rgLocalesToUse = ["en-us"];
      await DeckyPluginLoader.importPlugin(p.name, p.version, p.loadType, false);
    } finally {
      lm.m_rgLocalesToUse = saved;
    }
  })()
  ```
- Close the Quick Access Menu when you are done, so the user's screen is not left on the plugin page.

## Commit conventions

- **Commit per feature**, never one big commit at the end. Keep refactors (`refactor:`), fixes (`fix:`), dev tooling (`chore(dev):`) and docs (`docs:`) separate from features (`feat:`).
- Commit messages in English: the subject says what changed, the body says why. Follow the existing `git log`.
- When user-visible behaviour changes, update **both** `README.md` (English) and `README.zh-CN.md` (Simplified Chinese), keep them in sync, and keep the language switcher at the top.

## Checklist for a new feature

1. Implement the backend in `py_modules/sshwarden/`, running system commands through `proc.run()` and raising `UserError` for user-facing errors (add the code's translation to both languages in `src/i18n.ts`).
2. Add a CLI subcommand in `__main__.py` and a `_call()` forwarding method in `main.py`.
3. If the status needs a new field, update both `status.collect()` and the `Status` type in `src/api.ts`, without making the status call slower.
4. Add the wrapper in `src/api.ts`, then the section or dialog component, with its text in both languages in `src/i18n.ts`.
5. Add the matching undo logic to `cleanup.revert_all()`.
6. If the feature changes system state the watchdog does not cover, extend `dev/deck-guard/guard.sh` first.
7. Add unit tests (see "Build and checks"), run `pnpm typecheck`, `pnpm test` and `pnpm check:i18n`, test the backend CLI on a Deck with the watchdog installed, test the UI in both languages with `dev/cdp.py`, and confirm the watchdog reports `changed components: ''`.
8. Commit the feature on its own.

## Known TODOs

- The auto-off timer is a transient systemd timer and does not survive a reboot.

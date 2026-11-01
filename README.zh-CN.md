# SSH Warden

[English](README.md) | **简体中文**

[![CI](https://github.com/ArcherGu/decky-ssh-warden/actions/workflows/ci.yml/badge.svg)](https://github.com/ArcherGu/decky-ssh-warden/actions/workflows/ci.yml)

在 Steam Deck 的游戏模式下管理 SSH 服务的 [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) 插件。不用切到桌面模式、不用敲命令，就能开关 SSH、改端口、管密码，并且让 SSH 只在可信的网络上开放。

## 功能

| 区块 | 功能 |
| --- | --- |
| SSH 服务 | 开关 SSH；开机自启；定时自动关闭（15 分钟 / 30 分钟 / 1 小时 / 2 小时） |
| 状态 | 当前网络与可直接复制的连接命令、当前网络能否访问 SSH、当前连接、24 小时内登录失败次数、最近一次登录 |
| 连接设置 | 修改 SSH 端口 |
| 登录安全 | 允许/禁止密码登录；修改 `deck` 用户密码 |
| 公钥 | 列出可以登录的公钥并删除任意一个；从 Deck 上选择 `.pub` 文件导入公钥（可以用 U 盘或 SD 卡拷过去）；显示可以在电脑上运行的 `ssh-copy-id` 命令 |
| 可信网络 | 仅在勾选的网络上开放 SSH，其他网络（如公共 Wi-Fi）一律由防火墙拦截，VPN（如 Tailscale）也包括在内 |

界面语言跟随 Steam：Steam 设为简体中文时显示中文，其他语言显示英文。

关闭 SSH（手动关闭或定时自动关闭）只是不再接受新连接，已经建立的连接会保持，即使处于空闲状态。修改端口或密码登录设置时插件会自动重启 sshd，已有连接同样不受影响；修改密码不需要重启，下一次登录就生效。

## 安全设计

- **改配置不会把自己锁在外面**：插件只写自己的 sshd 配置文件 `/etc/ssh/sshd_config.d/05-ssh-warden.conf`，不改系统主配置。每次修改先用 `sshd -t` 校验，重启后还要确认 sshd 已在新端口监听，任一步失败都会自动恢复原配置。
- **没有公钥时不能关闭密码登录，关闭密码登录后不能删除最后一个公钥**：这两种情况都会导致无法登录，后端会拒绝，界面上对应的控件也会禁用。
- **拒绝私钥**：误选了私钥文件会直接报错，私钥内容不会被保存或写进日志。`authorized_keys` 以原子方式替换，`~/.ssh` 和文件由插件按 sshd 要求的权限创建。
- **密码不落地**：新密码通过标准输入交给 `chpasswd`，不会出现在进程参数或日志里。
- **改密码需要当前密码**：和 `passwd` 一样。Deck 上的任何程序都能和 Decky 的后端通信，没有这一步的话，它就能设置一个自己知道的密码，再用 `sudo` 拿到 root。
- **公共网络上隐身**：开启「仅在可信网络开放 SSH」后，可信网络被放进单独的防火墙区域 `sshwarden`（复制默认区域的全部规则，串流等功能不受影响），其他网络的区域对 SSH 端口使用 `drop`，端口扫描时看起来就像没有开放。
- **规则有账可查**：插件添加的每一条防火墙规则都记录在 `~/homebrew/settings/decky-ssh-warden/settings.json`，改端口、切换模式时先加新规则再删旧规则，不会出现空档，也不会留下垃圾。
- **卸载即还原**：卸载插件时会关闭可信网络模式、删除插件加的所有防火墙规则和 sshd 配置文件、取消定时关闭，SSH 回到系统默认（端口 22、允许密码登录）。公钥属于你自己的数据，会保留。
- **更新不丢设置**：Decky 在每次更新或重装插件前也会执行这个卸载步骤。SSH Warden 会先记下端口、密码登录、可信网络模式和定时关闭，新版本在 10 分钟内启动时自动恢复。更新进行的那几秒里，SSH 处于默认设置。
- **轮询只在面板打开时进行**：关闭快速访问菜单后不会在后台消耗资源。

插件以 `root` 权限运行（`plugin.json` 中的 `flags: ["root"]`），因为管理 sshd、修改密码和配置防火墙都需要 root。

## 已知限制

- 可信网络模式只列出 Wi-Fi 和有线网络。VPN 网卡（Tailscale、WireGuard 等）不属于任何防火墙区域，由默认区域处理，而开启该模式后默认区域会拦截 SSH。如果你通过 VPN 连接 Deck，请不要开启这个模式。
- sshd 只管理「端口」和「密码登录」两项，不处理 `AllowUsers` 等更细的选项。
- 定时自动关闭使用 systemd 临时定时器，重启 Deck 后不会保留。

## 安装

在电脑上构建并打包：

```bash
pnpm install
pnpm package      # 生成 out/decky-ssh-warden.zip
```

然后任选一种方式安装：

- 在 Deck 的 Decky「设置 → 开发者」中打开开发者模式，用「从 ZIP 安装插件」选择 `out/decky-ssh-warden.zip`。
- 或者通过 SSH 一键部署（sudo 时需要输入 deck 用户密码）：

  ```bash
  scripts/deploy.sh deck@<deck 的 IP>
  ```

## 开发

```bash
pnpm build        # 输出 dist/index.js
pnpm typecheck
pnpm test         # 前端和后端单元测试（后端需要 Python 3.10+）
```

每次推送都会在 CI 中运行类型检查、测试、翻译检查和打包。

- 前端：`src/`（React + `@decky/ui`），每个区块一个文件，放在 `src/sections/`。
- 后端：`main.py` 只做转发，逻辑都在 `py_modules/sshwarden/`。可以不经过界面直接在 Deck 上测试：

  ```bash
  cd ~/homebrew/plugins/decky-ssh-warden/py_modules
  sudo python3 -B -m sshwarden status
  sudo python3 -B -m sshwarden port 2222
  ```

参与本仓库开发的 AI agent 请先阅读 [AGENTS.md](AGENTS.md)。

### 远程测试的安全网：`dev/deck-guard`

远程测试 SSH 相关功能时，一次失误就可能让 Deck 再也连不上。`dev/deck-guard` 是一个开发期用的「看门狗」：

- 安装时给 sshd、`deck` 密码、firewalld、NetworkManager 区域和 `~/.ssh/authorized_keys` 拍一份「已知可用」快照。
- systemd 定时器每分钟检查一次；如果状态和快照不一致，**并且** `~/.ssh-warden-dev/heartbeat` 超过 5 分钟没有更新（也就是开发者已经连不上了），就恢复快照。
- 开发时每次通过 SSH 执行命令前 `touch` 一下心跳文件即可。

```bash
# 在 Deck 上以 root 运行
sudo bash dev/deck-guard/install.sh             # 安装并拍快照
sudo /var/lib/ssh-warden-dev/guard.sh status    # 查看状态
sudo bash dev/deck-guard/uninstall.sh           # 开发结束后卸载（会删除快照里的密码哈希副本）
```

> 看门狗会在 5 分钟没有心跳后还原所有 SSH 相关设置，所以**正常使用插件时不要安装它**，否则你在插件里改的设置会被还原。

`dev/cdp.py` 通过 Steam 的远程调试端口在 Deck 上执行 JS、点击开关和截图，用于检查界面。

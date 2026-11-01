# SSH Warden

在 Steam Deck 的游戏模式下管理 SSH 服务的 [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) 插件。

> 插件以 `root` 权限运行（`plugin.json` 中的 `flags: ["root"]`），因为管理 sshd、修改密码和配置防火墙都需要 root。

## 开发

```bash
pnpm install
pnpm build        # 输出 dist/index.js
pnpm typecheck
pnpm package      # 构建并打包为 out/decky-ssh-warden.zip
```

部署到 Deck（会通过 SSH 复制并重启 Decky，sudo 时需要输入 deck 用户密码）：

```bash
scripts/deploy.sh deck@<deck 的 IP>
```

也可以在 Decky 的「设置 → 开发者」里用「从 ZIP 安装插件」安装 `out/decky-ssh-warden.zip`。

/**
 * All text shown in the panel. The language follows Steam's: Simplified Chinese when Steam
 * is set to it, English for every other language.
 */

type Params = Record<string, string | number>;
type ErrorMessages = Record<string, (p: Params) => string>;

const en = {
  loading: "Reading SSH status…",
  loadFailed: (error: string) => `Couldn't read the SSH status: ${error}`,
  refreshFailed: (error: string) => `Couldn't refresh; what you see may be out of date: ${error}`,
  cancel: "Cancel",
  listSeparator: ", ",

  service: {
    title: "SSH Service",
    enable: "Enable SSH",
    running: "Running. Turning it off keeps open connections.",
    stopped: "Stopped",
    autooff: "Turn off automatically",
    autooffHint: "Stops accepting new connections at the chosen time; open ones stay",
    autooffAt: (clock: string) => `SSH turns off at ${clock}; open connections stay`,
    never: "Never",
    afterMinutes: (minutes: number) => `In ${minutes} minutes`,
    afterHours: (hours: number) => (hours === 1 ? "In 1 hour" : `In ${hours} hours`),
    remaining: (minutes: number) => `${minutes} min left`,
    autostart: "Start on boot",
  },

  status: {
    title: "Status",
    configError: "Config error",
    network: "Network",
    notConnected: "Not connected",
    noIPv4: "No IPv4 address",
    reachable: "Reachable",
    blocked: "Blocked",
    sessions: "Connections",
    sessionCount: (n: number) => String(n),
    failedLogins: "Failed logins (24 h)",
    failedCount: (n: number) => String(n),
    lastLogin: "Last login",
    loginFrom: (user: string, from: string) => `${user} from ${from}`,
    none: "None",
  },

  connection: {
    title: "Connection",
    port: "Port",
    changePort: "Change port",
    modalTitle: "Change SSH port",
    modalDescription:
      "SSH restarts on the new port right away; open connections stay. If it can't start, the old port is restored.",
    portLabel: "Port (1-65535, default 22)",
    save: "Save",
  },

  login: {
    title: "Login",
    passwordAuth: "Allow password login",
    noKeys: "No SSH public key yet. Add one below before turning password login off.",
    keysWithPassword: (n: number) =>
      `${n === 1 ? "1 public key" : `${n} public keys`} set up. Turn off to allow key login only.`,
    keysNotAccepted:
      "sshd doesn't accept keys on their own (PubkeyAuthentication, AuthorizedKeysFile or AuthenticationMethods), so password login must stay on",
    keysOnly: (n: number) => `Key login only (${n === 1 ? "1 public key" : `${n} public keys`})`,
    changePassword: (user: string) => `Change ${user}'s password`,
    passwordChanged: (user: string) => `Password for ${user} changed`,
    modalTitle: (user: string) => `Change password for ${user}`,
    modalDescription: "This is also the password for sudo and Desktop Mode. Open SSH connections stay.",
    currentPassword: "Current password",
    newPassword: "New password",
    confirmPassword: "Repeat new password",
    tooShort: (min: number) => `Use at least ${min} characters`,
    mismatch: "The passwords don't match",
    submit: "Change password",
  },

  keys: {
    title: "Public Keys",
    none: "No public keys yet",
    unsafe:
      "~/.ssh or ~/.ssh/authorized_keys is a symlink or not a plain file, so the plugin leaves it alone. Fix it in Desktop Mode.",
    unnamed: "Unnamed key",
    remove: "Remove",
    lastKeyLocked: "Password login is off, so the last key can't be removed",
    removeTitle: (name: string) => `Remove "${name}"?`,
    removeBody: (fingerprint: string) =>
      `Devices using this key will no longer be able to log in over SSH (open connections stay). Fingerprint: ${fingerprint}`,
    importFile: "Import from file",
    copyIdHint: (command: string) => `Or run this on your computer: ${command}`,
    fileHint: "Pick a .pub file. Copy it to the Deck first, e.g. on a USB drive or SD card.",
    imported: (added: number, skipped: number) =>
      added === 0
        ? "Every key in this file is already set up"
        : `Added ${added === 1 ? "1 public key" : `${added} public keys`}${skipped ? `; ${skipped} already set up` : ""}`,
  },

  trusted: {
    title: "Trusted Networks",
    mode: "SSH on trusted networks only",
    busy: "Configuring the firewall, this takes a few seconds…",
    noFirewall: "The firewall (firewalld) is not running, so this is unavailable",
    onHint:
      "Only the networks checked below can reach SSH. Others are blocked by the firewall, public Wi-Fi and VPNs (e.g. Tailscale) alike",
    offHint: "When on, only the networks checked below can reach SSH; VPNs such as Tailscale are blocked too",
    wifi: "Wi-Fi",
    ethernet: "Ethernet",
    connected: "Connected",
    enableTitle: "This network is not trusted",
    enableBody: (names: string) =>
      `New SSH connections from "${names}" will be blocked (open connections stay). Turn it on anyway?`,
    enableOk: "Turn on",
    untrustTitle: (name: string) => `Stop trusting "${name}"?`,
    untrustBody:
      "You are connected through this network. New SSH connections from it will be blocked (open connections stay).",
    untrustOk: "Stop trusting",
  },

  // Backend errors, by UserError code (py_modules/sshwarden).
  errors: {
    command_failed: (p) => `${p.command} failed: ${p.detail}`,
    password_length: (p) => `The password must be ${p.min} to ${p.max} characters long`,
    password_control_chars: () => "The password must not contain control characters such as line breaks",
    password_invalid_chars: () => "The password contains characters that cannot be used",
    wrong_password: () => "The current password is wrong",
    account_locked: () => "The deck account is locked; its password cannot be changed here",
    port_range: () => "The port must be between 1 and 65535",
    port_in_use: (p) => `Port ${p.port} is already used by ${p.owner}`,
    sshd_not_listening: (p) => `sshd did not start listening on port ${p.ports}; the previous settings were restored`,
    no_authorized_keys: () => "No SSH public key is set up; without password login nobody could log in over SSH",
    autooff_range: (p) => `Auto-off must be 1 to ${p.max} minutes away`,
    keys_not_accepted: () =>
      "sshd doesn't accept keys on their own (PubkeyAuthentication, AuthorizedKeysFile or AuthenticationMethods); password login must stay on",
    firewall_not_running: () => "The firewall (firewalld) is not running, so SSH can't be limited by network",
    key_file_unreadable: (p) => `Can't read ${p.file}: ${p.reason}`,
    key_file_private: (p) => `${p.file} is a private key; pick the matching .pub file`,
    key_file_invalid: (p) => `${p.file} contains no SSH public key`,
    key_not_found: () => "This public key no longer exists",
    keys_file_unsafe: () =>
      "~/.ssh or ~/.ssh/authorized_keys is a symlink or not a plain file, so the plugin leaves it alone",
    last_key: () => "This is the last public key and password login is off; removing it would lock everyone out",
  } satisfies ErrorMessages,
};

const zhCN: typeof en = {
  loading: "正在读取 SSH 状态…",
  loadFailed: (error) => `读取状态失败：${error}`,
  refreshFailed: (error) => `刷新失败，下面显示的可能是旧数据：${error}`,
  cancel: "取消",
  listSeparator: "、",

  service: {
    title: "SSH 服务",
    enable: "启用 SSH",
    running: "运行中，关闭后已建立的连接不会断开",
    stopped: "已停止",
    autooff: "自动关闭",
    autooffHint: "到时不再接受新连接，已建立的连接不受影响",
    autooffAt: (clock) => `将在 ${clock} 关闭 SSH，已建立的连接不受影响`,
    never: "不自动关闭",
    afterMinutes: (minutes) => `${minutes} 分钟后`,
    afterHours: (hours) => `${hours} 小时后`,
    remaining: (minutes) => `剩余 ${minutes} 分钟`,
    autostart: "开机自启",
  },

  status: {
    title: "状态",
    configError: "配置错误",
    network: "当前网络",
    notConnected: "未连接",
    noIPv4: "没有 IPv4 地址",
    reachable: "可访问",
    blocked: "已阻止",
    sessions: "当前连接",
    sessionCount: (n) => `${n} 个`,
    failedLogins: "24 小时内登录失败",
    failedCount: (n) => `${n} 次`,
    lastLogin: "最近登录",
    loginFrom: (user, from) => `${user} 来自 ${from}`,
    none: "无",
  },

  connection: {
    title: "连接设置",
    port: "端口",
    changePort: "修改端口",
    modalTitle: "修改 SSH 端口",
    modalDescription: "保存后 SSH 会立即切换到新端口，已建立的连接不受影响。新配置无法启动时会自动恢复原端口。",
    portLabel: "端口（1-65535，默认 22）",
    save: "保存",
  },

  login: {
    title: "登录安全",
    passwordAuth: "允许密码登录",
    noKeys: "未配置 SSH 公钥，需先在下方添加公钥才能关闭密码登录",
    keysWithPassword: (n) => `已配置 ${n} 个公钥，关闭后只能用公钥登录`,
    keysNotAccepted:
      "sshd 目前不接受单独用公钥登录（PubkeyAuthentication、AuthorizedKeysFile 或 AuthenticationMethods 设置），不能关闭密码登录",
    keysOnly: (n) => `只允许公钥登录（已配置 ${n} 个公钥）`,
    changePassword: (user) => `修改 ${user} 密码`,
    passwordChanged: (user) => `${user} 的密码已修改`,
    modalTitle: (user) => `修改 ${user} 用户的密码`,
    modalDescription: "这也是 sudo 和桌面模式使用的密码。已建立的 SSH 连接不受影响。",
    currentPassword: "当前密码",
    newPassword: "新密码",
    confirmPassword: "再次输入新密码",
    tooShort: (min) => `密码至少需要 ${min} 个字符`,
    mismatch: "两次输入的密码不一致",
    submit: "修改密码",
  },

  keys: {
    title: "公钥",
    none: "还没有公钥",
    unsafe: "~/.ssh 或 ~/.ssh/authorized_keys 是符号链接或不是普通文件，插件不会读写它。请在桌面模式下处理。",
    unnamed: "未命名公钥",
    remove: "删除",
    lastKeyLocked: "密码登录已关闭，不能删除最后一个公钥",
    removeTitle: (name) => `删除「${name}」？`,
    removeBody: (fingerprint) => `使用这个公钥的设备将无法再通过 SSH 登录（已建立的连接不受影响）。指纹：${fingerprint}`,
    importFile: "从文件导入",
    copyIdHint: (command) => `也可以在电脑上运行：${command}`,
    fileHint: "选择 .pub 文件。可以先用 U 盘或 SD 卡拷到 Deck 上。",
    imported: (added, skipped) =>
      added === 0 ? "文件里的公钥都已存在" : `已添加 ${added} 个公钥${skipped ? `，${skipped} 个已存在` : ""}`,
  },

  trusted: {
    title: "可信网络",
    mode: "仅在可信网络开放 SSH",
    busy: "正在配置防火墙，需要几秒钟…",
    noFirewall: "防火墙（firewalld）没有运行，无法使用此功能",
    onHint: "只有下面勾选的网络可以连接 SSH，其他网络会被防火墙拦截，包括公共 Wi-Fi 和 VPN（如 Tailscale）",
    offHint: "开启后，只有下面勾选的网络可以连接 SSH，VPN（如 Tailscale）也会被拦截",
    wifi: "Wi-Fi",
    ethernet: "有线网络",
    connected: "当前连接",
    enableTitle: "当前网络不在可信列表中",
    enableBody: (names) => `开启后将无法从「${names}」建立新的 SSH 连接（已建立的连接不受影响）。确定开启吗？`,
    enableOk: "仍然开启",
    untrustTitle: (name) => `取消信任「${name}」`,
    untrustBody: "这是当前连接的网络，取消信任后将无法从它建立新的 SSH 连接（已建立的连接不受影响）。确定吗？",
    untrustOk: "取消信任",
  },

  errors: {
    command_failed: (p) => `${p.command} 失败：${p.detail}`,
    password_length: (p) => `密码长度需在 ${p.min} 到 ${p.max} 个字符之间`,
    password_control_chars: () => "密码不能包含换行等控制字符",
    password_invalid_chars: () => "密码包含无法使用的字符",
    wrong_password: () => "当前密码不正确",
    account_locked: () => "deck 账户已被锁定，不能在这里修改密码",
    port_range: () => "端口需在 1 到 65535 之间",
    port_in_use: (p) => `端口 ${p.port} 已被 ${p.owner} 占用`,
    sshd_not_listening: (p) => `sshd 没有在端口 ${p.ports} 上启动，已恢复原配置`,
    no_authorized_keys: () => "还没有配置 SSH 公钥，关闭密码登录后将无法再通过 SSH 登录",
    autooff_range: (p) => `自动关闭时间需在 1 到 ${p.max} 分钟之间`,
    keys_not_accepted: () =>
      "sshd 目前不接受单独用公钥登录（PubkeyAuthentication、AuthorizedKeysFile 或 AuthenticationMethods 设置），不能关闭密码登录",
    firewall_not_running: () => "防火墙（firewalld）没有运行，无法按网络限制 SSH",
    key_file_unreadable: (p) => `无法读取 ${p.file}：${p.reason}`,
    key_file_private: (p) => `${p.file} 是私钥，请选择对应的 .pub 文件`,
    key_file_invalid: (p) => `${p.file} 里没有 SSH 公钥`,
    key_not_found: () => "这个公钥已经不存在了",
    keys_file_unsafe: () => "~/.ssh 或 ~/.ssh/authorized_keys 是符号链接或不是普通文件，插件不会读写它",
    last_key: () => "这是最后一个公钥，而且密码登录已关闭，删除后将无法再通过 SSH 登录",
  },
};

/** Steam's UI language as a lower-case locale, e.g. "zh-cn" or "en-us". */
function steamLocale(): string {
  // globalThis is window in Steam, and also exists where the tests run (Node).
  const steam = globalThis as { LocalizationManager?: { m_rgLocalesToUse?: string[] } };
  return (steam.LocalizationManager?.m_rgLocalesToUse?.[0] ?? globalThis.navigator?.language ?? "").toLowerCase();
}

const locale = steamLocale();

export const t = locale.startsWith("zh-cn") || locale.startsWith("zh-hans") ? zhCN : en;

/** A backend error in the panel's language; unknown codes fall back to the backend's English text. */
export function errorMessage(code: string | undefined, params: Params | undefined, fallback: string) {
  const message = code ? (t.errors as ErrorMessages)[code] : undefined;
  return message ? message(params ?? {}) : fallback;
}

import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { Status } from "../api";
import { formatTime } from "../format";

const OK = "#5ba32b";
const WARN = "#e0a33b";
const MUTED = "#8b929a";

function sshCommand(status: Status, address: string) {
  const port = status.ports[0] ?? 22;
  return `ssh ${status.user}@${address}${port === 22 ? "" : ` -p ${port}`}`;
}

export function StatusSection({ status }: { status: Status }) {
  const lastLogin = status.logins.recent[0];
  return (
    <PanelSection title="状态">
      {status.config_error && (
        <PanelSectionRow>
          <Field label="配置错误" description={status.config_error} bottomSeparator="none" />
        </PanelSectionRow>
      )}

      {status.networks.length === 0 && (
        <PanelSectionRow>
          <Field label="当前网络" bottomSeparator="none">
            <span style={{ color: MUTED }}>未连接</span>
          </Field>
        </PanelSectionRow>
      )}
      {status.networks.map((n) => (
        <PanelSectionRow key={n.uuid}>
          <Field
            label={n.name}
            description={n.addresses.map((a) => sshCommand(status, a)).join("\n") || "没有 IPv4 地址"}
            bottomSeparator="none"
          >
            <span style={{ color: n.ssh_allowed ? OK : WARN }}>{n.ssh_allowed ? "可访问" : "已阻止"}</span>
          </Field>
        </PanelSectionRow>
      ))}

      <PanelSectionRow>
        <Field
          label="当前连接"
          description={status.sessions.length ? Array.from(new Set(status.sessions)).join("、") : undefined}
          bottomSeparator="none"
        >
          {status.sessions.length} 个
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="24 小时内登录失败" bottomSeparator="none">
          <span style={{ color: status.logins.failed ? WARN : undefined }}>{status.logins.failed} 次</span>
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field
          label="最近登录"
          description={lastLogin ? `${lastLogin.user} 来自 ${lastLogin.from}` : undefined}
          bottomSeparator="none"
        >
          {lastLogin ? formatTime(lastLogin.time) : "无"}
        </Field>
      </PanelSectionRow>
    </PanelSection>
  );
}

import { Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { Status } from "../api";
import { formatTime, sshCommand } from "../format";
import { t } from "../i18n";

const OK = "#5ba32b";
const WARN = "#e0a33b";
const MUTED = "#8b929a";

export function StatusSection({ status }: { status: Status }) {
  const lastLogin = status.logins.recent[0];
  return (
    <PanelSection title={t.status.title}>
      {status.config_error && (
        <PanelSectionRow>
          <Field label={t.status.configError} description={status.config_error} bottomSeparator="none" />
        </PanelSectionRow>
      )}

      {status.networks.length === 0 && (
        <PanelSectionRow>
          <Field label={t.status.network} bottomSeparator="none">
            <span style={{ color: MUTED }}>{t.status.notConnected}</span>
          </Field>
        </PanelSectionRow>
      )}
      {status.networks.map((n) => (
        <PanelSectionRow key={n.uuid}>
          <Field
            label={n.name}
            description={n.addresses.map((a) => sshCommand("ssh", status.user, a, status.ports[0] ?? 22)).join("\n") || t.status.noIPv4}
            bottomSeparator="none"
          >
            <span style={{ color: n.ssh_allowed ? OK : WARN }}>{n.ssh_allowed ? t.status.reachable : t.status.blocked}</span>
          </Field>
        </PanelSectionRow>
      ))}

      <PanelSectionRow>
        <Field
          label={t.status.sessions}
          description={status.sessions.length ? Array.from(new Set(status.sessions)).join(t.listSeparator) : undefined}
          bottomSeparator="none"
        >
          {t.status.sessionCount(status.sessions.length)}
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label={t.status.failedLogins} bottomSeparator="none">
          <span style={{ color: status.logins.failed ? WARN : undefined }}>{t.status.failedCount(status.logins.failed)}</span>
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field
          label={t.status.lastLogin}
          description={lastLogin ? t.status.loginFrom(lastLogin.user, lastLogin.from) : undefined}
          bottomSeparator="none"
        >
          {lastLogin ? formatTime(lastLogin.time) : t.status.none}
        </Field>
      </PanelSectionRow>
    </PanelSection>
  );
}

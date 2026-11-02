import { ButtonItem, Field, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { repairFirewall, Status } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { formatTime, sshCommand } from "../format";
import { t } from "../i18n";
import { useAction } from "../useAction";

const OK = "#5ba32b";
const WARN = "#e0a33b";
const MUTED = "#8b929a";

export function StatusSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const { busy, run } = useAction(refresh);
  const lastLogin = status.logins.recent[0];

  const repair = () => {
    // In trusted mode a missing drop rule may be what lets the current network in right now.
    // status.trusted_mode is the saved mode, the one the repair applies.
    const exposed = status.trusted_mode ? status.networks.filter((n) => !n.trusted && n.ssh_allowed).map((n) => n.name) : [];
    if (exposed.length === 0) {
      run(repairFirewall);
      return;
    }
    showModal(
      <ConfirmDialog
        title={t.status.repairTitle}
        description={t.status.repairBody(exposed.join(t.listSeparator))}
        okText={t.status.repair}
        onConfirm={() => run(repairFirewall)}
      />,
    );
  };
  return (
    <PanelSection title={t.status.title}>
      {status.config_error && (
        <PanelSectionRow>
          <Field label={t.status.configError} description={status.config_error} bottomSeparator="none" />
        </PanelSectionRow>
      )}
      {status.firewall_out_of_sync > 0 && (
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            label={<span style={{ color: WARN }}>{t.status.firewallOutOfSync}</span>}
            description={t.status.firewallOutOfSyncHint(status.firewall_out_of_sync)}
            disabled={busy}
            onClick={repair}
          >
            {t.status.repair}
          </ButtonItem>
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

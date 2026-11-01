import { PanelSection, PanelSectionRow, showModal, ToggleField } from "@decky/ui";
import { setNetworkTrusted, setTrustedMode, Status } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { t } from "../i18n";
import { useAction } from "../useAction";

function modeHint(status: Status) {
  if (!status.firewall) return t.trusted.noFirewall;
  return status.trusted_mode ? t.trusted.onHint : t.trusted.offHint;
}

export function TrustedSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const { busy, run } = useAction(refresh);

  const toggleMode = (on: boolean) => {
    const current = status.networks.filter((n) => !n.trusted).map((n) => n.name);
    if (!on || current.length === 0) {
      run(() => setTrustedMode(on));
      return;
    }
    // Turning this on while connected through an untrusted network cuts off new SSH logins from it.
    showModal(
      <ConfirmDialog
        title={t.trusted.enableTitle}
        description={t.trusted.enableBody(current.join(t.listSeparator))}
        okText={t.trusted.enableOk}
        onConfirm={() => run(() => setTrustedMode(true))}
      />,
    );
  };

  const toggleNetwork = (network: Status["saved_networks"][number], on: boolean) => {
    if (on || !status.trusted_mode || !network.active) {
      run(() => setNetworkTrusted(network.uuid, on));
      return;
    }
    showModal(
      <ConfirmDialog
        title={t.trusted.untrustTitle(network.name)}
        description={t.trusted.untrustBody}
        okText={t.trusted.untrustOk}
        onConfirm={() => run(() => setNetworkTrusted(network.uuid, false))}
      />,
    );
  };

  return (
    <PanelSection title={t.trusted.title}>
      <PanelSectionRow>
        <ToggleField
          label={t.trusted.mode}
          description={busy ? t.trusted.busy : modeHint(status)}
          checked={status.trusted_mode}
          disabled={busy || !status.firewall}
          onChange={toggleMode}
        />
      </PanelSectionRow>
      {status.saved_networks.map((n) => (
        <PanelSectionRow key={n.uuid}>
          <ToggleField
            label={n.name}
            description={[n.type === "wifi" ? t.trusted.wifi : t.trusted.ethernet, n.active ? t.trusted.connected : ""]
              .filter(Boolean)
              .join(" · ")}
            checked={n.trusted}
            disabled={busy}
            onChange={(on) => toggleNetwork(n, on)}
          />
        </PanelSectionRow>
      ))}
    </PanelSection>
  );
}

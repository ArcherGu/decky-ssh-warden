import { PanelSection, PanelSectionRow, showModal, ToggleField } from "@decky/ui";
import { setNetworkTrusted, setTrustedMode, Status } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useAction } from "../useAction";

function modeHint(status: Status) {
  if (!status.firewall) return "防火墙（firewalld）没有运行，无法使用此功能";
  return status.trusted_mode
    ? "只有下面勾选的网络可以连接 SSH，其他网络（如公共 Wi-Fi）会被防火墙拦截"
    : "开启后，只有下面勾选的网络可以连接 SSH";
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
        title="当前网络不在可信列表中"
        description={`开启后将无法从「${current.join("、")}」建立新的 SSH 连接（已建立的连接不受影响）。确定开启吗？`}
        okText="仍然开启"
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
        title={`取消信任「${network.name}」`}
        description="这是当前连接的网络，取消信任后将无法从它建立新的 SSH 连接（已建立的连接不受影响）。确定吗？"
        okText="取消信任"
        onConfirm={() => run(() => setNetworkTrusted(network.uuid, false))}
      />,
    );
  };

  return (
    <PanelSection title="可信网络">
      <PanelSectionRow>
        <ToggleField
          label="仅在可信网络开放 SSH"
          description={busy ? "正在配置防火墙，需要几秒钟…" : modeHint(status)}
          checked={status.trusted_mode}
          disabled={busy || !status.firewall}
          onChange={toggleMode}
        />
      </PanelSectionRow>
      {status.saved_networks.map((n) => (
        <PanelSectionRow key={n.uuid}>
          <ToggleField
            label={n.name}
            description={[n.type === "wifi" ? "Wi-Fi" : "有线网络", n.active ? "当前连接" : ""].filter(Boolean).join(" · ")}
            checked={n.trusted}
            disabled={busy}
            onChange={(on) => toggleNetwork(n, on)}
          />
        </PanelSectionRow>
      ))}
    </PanelSection>
  );
}

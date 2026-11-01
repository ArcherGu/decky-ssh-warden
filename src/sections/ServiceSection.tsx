import { PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { useState } from "react";
import { notifyError, setAutostart, setRunning, Status } from "../api";

export function ServiceSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);

  const apply = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
    } catch (e) {
      notifyError(e);
    } finally {
      await refresh();
      setBusy(false);
    }
  };

  return (
    <PanelSection title="SSH 服务">
      <PanelSectionRow>
        <ToggleField
          label="启用 SSH"
          description={status.running ? "运行中，关闭后已建立的连接不会断开" : "已停止"}
          checked={status.running}
          disabled={busy}
          onChange={(on) => apply(() => setRunning(on))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="开机自启"
          checked={status.autostart}
          disabled={busy}
          onChange={(on) => apply(() => setAutostart(on))}
        />
      </PanelSectionRow>
    </PanelSection>
  );
}

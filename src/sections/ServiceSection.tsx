import { DropdownItem, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { setAutooff, setAutostart, setRunning, Status } from "../api";
import { formatClock, minutesUntil } from "../format";
import { useAction } from "../useAction";

const AUTOOFF_CHOICES = [
  { data: 0, label: "不自动关闭" },
  { data: 15, label: "15 分钟后" },
  { data: 30, label: "30 分钟后" },
  { data: 60, label: "1 小时后" },
  { data: 120, label: "2 小时后" },
];
// Shown as the selected entry while a timer is pending; picking it does nothing.
const PENDING = -1;

export function ServiceSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const { busy, run: apply } = useAction(refresh);

  const autooffAt = status.autooff_at;
  const autooffOptions = autooffAt
    ? [{ data: PENDING, label: `剩余 ${minutesUntil(autooffAt)} 分钟` }, ...AUTOOFF_CHOICES]
    : AUTOOFF_CHOICES;

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
      {status.running && (
        <PanelSectionRow>
          <DropdownItem
            label="自动关闭"
            layout="below"
            description={autooffAt ? `将在 ${formatClock(autooffAt)} 自动关闭 SSH` : "到时自动停止 SSH，适合临时开启"}
            rgOptions={autooffOptions}
            selectedOption={autooffAt ? PENDING : 0}
            disabled={busy}
            onChange={(option) => option.data !== PENDING && apply(() => setAutooff(option.data))}
          />
        </PanelSectionRow>
      )}
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

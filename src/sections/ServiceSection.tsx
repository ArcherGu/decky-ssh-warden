import { DropdownItem, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { setAutooff, setAutostart, setRunning, Status } from "../api";
import { formatClock, minutesUntil } from "../format";
import { t } from "../i18n";
import { useAction } from "../useAction";

const AUTOOFF_CHOICES = [
  { data: 0, label: t.service.never },
  { data: 15, label: t.service.afterMinutes(15) },
  { data: 30, label: t.service.afterMinutes(30) },
  { data: 60, label: t.service.afterHours(1) },
  { data: 120, label: t.service.afterHours(2) },
];
// Shown as the selected entry while a timer is pending; picking it does nothing.
const PENDING = -1;

export function ServiceSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const { busy, run: apply } = useAction(refresh);

  const autooffAt = status.autooff_at;
  const autooffOptions = autooffAt
    ? [{ data: PENDING, label: t.service.remaining(minutesUntil(autooffAt)) }, ...AUTOOFF_CHOICES]
    : AUTOOFF_CHOICES;

  return (
    <PanelSection title={t.service.title}>
      <PanelSectionRow>
        <ToggleField
          label={t.service.enable}
          description={status.running ? t.service.running : t.service.stopped}
          checked={status.running}
          disabled={busy}
          onChange={(on) => apply(() => setRunning(on))}
        />
      </PanelSectionRow>
      {status.running && (
        <PanelSectionRow>
          <DropdownItem
            label={t.service.autooff}
            layout="below"
            description={autooffAt ? t.service.autooffAt(formatClock(autooffAt)) : t.service.autooffHint}
            rgOptions={autooffOptions}
            selectedOption={autooffAt ? PENDING : 0}
            disabled={busy}
            onChange={(option) => option.data !== PENDING && apply(() => setAutooff(option.data))}
          />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ToggleField
          label={t.service.autostart}
          checked={status.autostart}
          disabled={busy}
          onChange={(on) => apply(() => setAutostart(on))}
        />
      </PanelSectionRow>
    </PanelSection>
  );
}

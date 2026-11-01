import { ButtonItem, Field, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { setPort, Status } from "../api";
import { PortModal } from "../components/PortModal";
import { t } from "../i18n";
import { useAction } from "../useAction";

export function ConnectionSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const { busy, run } = useAction(refresh);
  const port = status.ports[0] ?? 22;

  return (
    <PanelSection title={t.connection.title}>
      <PanelSectionRow>
        <Field label={t.connection.port} bottomSeparator="none">
          {status.ports.join(", ")}
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={busy}
          onClick={() => showModal(<PortModal current={port} onSubmit={(p) => run(() => setPort(p))} />)}
        >
          {t.connection.changePort}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

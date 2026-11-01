import { ButtonItem, DialogButton, Field, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { FileSelectionType, openFilePicker, toaster } from "@decky/api";
import { importKeys, PublicKey, removeKey, Status } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { sshCommand } from "../format";
import { t } from "../i18n";
import { useAction } from "../useAction";

const shortFingerprint = (fingerprint: string) => `${fingerprint.slice(0, 19)}…`;
// ButtonItem's inline button is too wide for the Quick Access Menu next to a key name.
const REMOVE_BUTTON = { minWidth: 0, width: "auto", padding: "6px 14px" };

function importHint(status: Status) {
  const address = status.networks.flatMap((n) => n.addresses)[0];
  // ssh-copy-id is the quickest way, but it logs in with the password.
  if (status.password_auth && status.running && address) {
    return t.keys.copyIdHint(sshCommand("ssh-copy-id", status.user, address, status.ports[0] ?? 22));
  }
  return t.keys.fileHint;
}

export function KeysSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const { busy, run } = useAction(refresh);
  // Without password login the last key is the only way in.
  const lastKeyLocked = !status.password_auth && status.keys.length === 1;

  const importFromFile = async () => {
    let path: string;
    try {
      const picked = await openFilePicker(FileSelectionType.FILE, "/home/deck", true, true, undefined, ["pub"], false, true);
      path = picked.realpath;
    } catch {
      return; // the picker rejects when it is cancelled
    }
    run(async () => {
      const { added, skipped } = await importKeys(path);
      toaster.toast({ title: "SSH Warden", body: t.keys.imported(added, skipped) });
    });
  };

  const confirmRemove = (key: PublicKey) =>
    showModal(
      <ConfirmDialog
        title={t.keys.removeTitle(key.comment || t.keys.unnamed)}
        description={t.keys.removeBody(key.fingerprint)}
        okText={t.keys.remove}
        onConfirm={() => run(() => removeKey(key.fingerprint))}
      />,
    );

  return (
    <PanelSection title={t.keys.title}>
      {status.keys_unsafe && (
        <PanelSectionRow>
          <Field label={t.keys.unsafe} bottomSeparator="none" />
        </PanelSectionRow>
      )}
      {status.keys.length === 0 && !status.keys_unsafe && (
        <PanelSectionRow>
          <Field label={t.keys.none} bottomSeparator="none" />
        </PanelSectionRow>
      )}
      {status.keys.map((key) => (
        <PanelSectionRow key={key.fingerprint}>
          <Field
            label={key.comment || t.keys.unnamed}
            description={lastKeyLocked ? t.keys.lastKeyLocked : `${key.type} · ${shortFingerprint(key.fingerprint)}`}
            childrenContainerWidth="min"
          >
            <DialogButton style={REMOVE_BUTTON} disabled={busy || lastKeyLocked} onClick={() => confirmRemove(key)}>
              {t.keys.remove}
            </DialogButton>
          </Field>
        </PanelSectionRow>
      ))}
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          description={importHint(status)}
          disabled={busy || status.keys_unsafe}
          onClick={importFromFile}
        >
          {t.keys.importFile}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

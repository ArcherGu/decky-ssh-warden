import { ButtonItem, PanelSection, PanelSectionRow, showModal, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { changePassword, setPasswordAuth, Status } from "../api";
import { PasswordModal } from "../components/PasswordModal";
import { t } from "../i18n";
import { useAction } from "../useAction";

function passwordAuthHint(status: Status) {
  const count = status.keys.length;
  if (status.keys_unsafe) return t.keys.unsafe;
  if (count === 0) return t.login.noKeys;
  if (status.password_auth && !status.key_login) return t.login.keysNotAccepted;
  return status.password_auth ? t.login.keysWithPassword(count) : t.login.keysOnly(count);
}

export function LoginSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const { busy, run } = useAction(refresh);
  // Never offer to switch password login off when that would lock everyone out.
  const lockedOn = status.password_auth && !status.key_login;

  const submitPassword = (current: string, password: string) =>
    run(async () => {
      await changePassword(current, password);
      toaster.toast({ title: "SSH Warden", body: t.login.passwordChanged(status.user) });
    });

  return (
    <PanelSection title={t.login.title}>
      <PanelSectionRow>
        <ToggleField
          label={t.login.passwordAuth}
          description={passwordAuthHint(status)}
          checked={status.password_auth}
          disabled={busy || lockedOn}
          onChange={(on) => run(() => setPasswordAuth(on))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={busy}
          onClick={() => showModal(<PasswordModal user={status.user} askCurrent={status.password_set} onSubmit={submitPassword} />)}
        >
          {t.login.changePassword(status.user)}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

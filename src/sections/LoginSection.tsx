import { ButtonItem, PanelSection, PanelSectionRow, showModal, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { changePassword, setPasswordAuth, Status } from "../api";
import { PasswordModal } from "../components/PasswordModal";
import { useAction } from "../useAction";

function passwordAuthHint(status: Status) {
  if (status.key_count === 0) return "未配置 SSH 公钥，需先添加公钥才能关闭密码登录";
  return status.password_auth
    ? `已配置 ${status.key_count} 个公钥，关闭后只能用公钥登录`
    : `只允许公钥登录（已配置 ${status.key_count} 个公钥）`;
}

export function LoginSection({ status, refresh }: { status: Status; refresh: () => Promise<void> }) {
  const { busy, run } = useAction(refresh);
  // Never offer to switch password login off when that would lock everyone out.
  const lockedOn = status.password_auth && status.key_count === 0;

  const submitPassword = (password: string) =>
    run(async () => {
      await changePassword(password);
      toaster.toast({ title: "SSH Warden", body: `${status.user} 的密码已修改` });
    });

  return (
    <PanelSection title="登录安全">
      <PanelSectionRow>
        <ToggleField
          label="允许密码登录"
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
          onClick={() => showModal(<PasswordModal user={status.user} onSubmit={submitPassword} />)}
        >
          修改 {status.user} 密码
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

import { ConfirmModal, TextField } from "@decky/ui";
import { useState } from "react";

const MIN_LENGTH = 8;

interface Props {
  user: string;
  onSubmit: (password: string) => void;
  closeModal?: () => void;
}

export function PasswordModal({ user, onSubmit, closeModal }: Props) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  let problem = "";
  if (password.length > 0 && password.length < MIN_LENGTH) problem = `密码至少需要 ${MIN_LENGTH} 个字符`;
  else if (confirm.length > 0 && confirm !== password) problem = "两次输入的密码不一致";
  const valid = password.length >= MIN_LENGTH && password === confirm;

  return (
    <ConfirmModal
      strTitle={`修改 ${user} 用户的密码`}
      strDescription="这也是 sudo 和桌面模式使用的密码。已建立的 SSH 连接不受影响。"
      strOKButtonText="修改密码"
      strCancelButtonText="取消"
      bOKDisabled={!valid}
      // ConfirmModal does not close itself here, so close explicitly.
      onOK={() => {
        closeModal?.();
        onSubmit(password);
      }}
      onCancel={() => closeModal?.()}
      closeModal={closeModal}
    >
      <TextField label="新密码" bIsPassword value={password} onChange={(e) => setPassword(e.target.value)} />
      <TextField label="再次输入新密码" bIsPassword value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      {problem && <div style={{ color: "#e0a33b", marginTop: 8 }}>{problem}</div>}
    </ConfirmModal>
  );
}

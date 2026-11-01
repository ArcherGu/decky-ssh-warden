import { ConfirmModal, TextField } from "@decky/ui";
import { useState } from "react";
import { t } from "../i18n";

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
  if (password.length > 0 && password.length < MIN_LENGTH) problem = t.login.tooShort(MIN_LENGTH);
  else if (confirm.length > 0 && confirm !== password) problem = t.login.mismatch;
  const valid = password.length >= MIN_LENGTH && password === confirm;

  return (
    <ConfirmModal
      strTitle={t.login.modalTitle(user)}
      strDescription={t.login.modalDescription}
      strOKButtonText={t.login.submit}
      strCancelButtonText={t.cancel}
      bOKDisabled={!valid}
      // ConfirmModal does not close itself here, so close explicitly.
      onOK={() => {
        closeModal?.();
        onSubmit(password);
      }}
      onCancel={() => closeModal?.()}
      closeModal={closeModal}
    >
      <TextField label={t.login.newPassword} bIsPassword value={password} onChange={(e) => setPassword(e.target.value)} />
      <TextField label={t.login.confirmPassword} bIsPassword value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      {problem && <div style={{ color: "#e0a33b", marginTop: 8 }}>{problem}</div>}
    </ConfirmModal>
  );
}

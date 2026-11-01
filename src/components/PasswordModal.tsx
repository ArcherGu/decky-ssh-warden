import { ConfirmModal, TextField } from "@decky/ui";
import { useState } from "react";
import { t } from "../i18n";

const MIN_LENGTH = 8;

interface Props {
  user: string;
  /** Ask for the current password (required by the backend once one is set). */
  askCurrent: boolean;
  onSubmit: (current: string, password: string) => void;
  closeModal?: () => void;
}

export function PasswordModal({ user, askCurrent, onSubmit, closeModal }: Props) {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  let problem = "";
  if (password.length > 0 && password.length < MIN_LENGTH) problem = t.login.tooShort(MIN_LENGTH);
  else if (confirm.length > 0 && confirm !== password) problem = t.login.mismatch;
  const valid = (!askCurrent || current.length > 0) && password.length >= MIN_LENGTH && password === confirm;

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
        onSubmit(current, password);
      }}
      onCancel={() => closeModal?.()}
      closeModal={closeModal}
    >
      {askCurrent && (
        <TextField label={t.login.currentPassword} bIsPassword value={current} onChange={(e) => setCurrent(e.target.value)} />
      )}
      <TextField label={t.login.newPassword} bIsPassword value={password} onChange={(e) => setPassword(e.target.value)} />
      <TextField label={t.login.confirmPassword} bIsPassword value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      {problem && <div style={{ color: "#e0a33b", marginTop: 8 }}>{problem}</div>}
    </ConfirmModal>
  );
}

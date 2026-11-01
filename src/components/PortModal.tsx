import { ConfirmModal, TextField } from "@decky/ui";
import { useState } from "react";
import { t } from "../i18n";

interface Props {
  current: number;
  onSubmit: (port: number) => void;
  closeModal?: () => void;
}

export function PortModal({ current, onSubmit, closeModal }: Props) {
  const [value, setValue] = useState(String(current));
  const port = Number(value);
  const valid = /^\d+$/.test(value) && port >= 1 && port <= 65535;

  return (
    <ConfirmModal
      strTitle={t.connection.modalTitle}
      strDescription={t.connection.modalDescription}
      strOKButtonText={t.connection.save}
      strCancelButtonText={t.cancel}
      bOKDisabled={!valid || port === current}
      // ConfirmModal does not close itself here, so close explicitly.
      onOK={() => {
        closeModal?.();
        onSubmit(port);
      }}
      onCancel={() => closeModal?.()}
      closeModal={closeModal}
    >
      <TextField
        label={t.connection.portLabel}
        value={value}
        mustBeNumeric
        rangeMin={1}
        rangeMax={65535}
        onChange={(e) => setValue(e.target.value.trim())}
      />
    </ConfirmModal>
  );
}

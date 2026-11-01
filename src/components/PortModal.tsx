import { ConfirmModal, TextField } from "@decky/ui";
import { useState } from "react";

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
      strTitle="修改 SSH 端口"
      strDescription="保存后 SSH 会立即切换到新端口，已建立的连接不受影响。新配置无法启动时会自动恢复原端口。"
      strOKButtonText="保存"
      strCancelButtonText="取消"
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
        label="端口（1-65535，默认 22）"
        value={value}
        mustBeNumeric
        rangeMin={1}
        rangeMax={65535}
        onChange={(e) => setValue(e.target.value.trim())}
      />
    </ConfirmModal>
  );
}

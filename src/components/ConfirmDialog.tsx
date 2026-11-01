import { ConfirmModal } from "@decky/ui";
import { t } from "../i18n";

interface Props {
  title: string;
  description: string;
  okText: string;
  onConfirm: () => void;
  closeModal?: () => void;
}

/** A yes/no dialog for showModal() that closes itself on either button. */
export function ConfirmDialog({ title, description, okText, onConfirm, closeModal }: Props) {
  return (
    <ConfirmModal
      strTitle={title}
      strDescription={description}
      strOKButtonText={okText}
      strCancelButtonText={t.cancel}
      onOK={() => {
        closeModal?.();
        onConfirm();
      }}
      onCancel={() => closeModal?.()}
      closeModal={closeModal}
    />
  );
}

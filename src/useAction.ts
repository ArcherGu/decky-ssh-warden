import { useState } from "react";
import { notifyError } from "./api";

/** Runs one backend action at a time: shows errors as toasts and refreshes the status after. */
export function useAction(refresh: () => Promise<void>) {
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
    } catch (e) {
      notifyError(e);
    } finally {
      await refresh();
      setBusy(false);
    }
  };

  return { busy, run };
}

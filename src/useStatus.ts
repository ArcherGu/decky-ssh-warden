import { useCallback, useEffect, useRef, useState } from "react";
import { getStatus, Status } from "./api";

const POLL_MS = 3000;

/** Polls the backend status while the panel is open. */
export function useStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Only the latest request may update the state, so a slow poll that returns after an
  // action's refresh cannot put an older status back (toggles would jump back).
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++latest.current;
    try {
      const next = await getStatus();
      if (id === latest.current) {
        setStatus(next);
        setError(null);
      }
    } catch (e) {
      if (id === latest.current) setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    // Schedule the next poll only after the last one finished, so slow ones cannot pile up
    // (a firewall reload can make a status call take seconds).
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const poll = async () => {
      await refresh();
      if (!stopped) timer = setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [refresh]);

  return { status, error, refresh };
}

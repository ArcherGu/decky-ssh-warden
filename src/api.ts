import { callable, toaster } from "@decky/api";

export interface Network {
  name: string;
  uuid: string;
  type: "wifi" | "ethernet";
  device: string;
  addresses: string[];
  zone: string | null;
  ssh_allowed: boolean;
}

export interface Login {
  time: number;
  method: string;
  user: string;
  from: string;
}

export interface Status {
  user: string;
  running: boolean;
  autostart: boolean;
  autooff_at: number | null;
  ports: number[];
  config_error: string | null;
  password_auth: boolean;
  key_count: number;
  sessions: string[];
  logins: { recent: Login[]; failed: number };
  firewall: boolean;
  networks: Network[];
}

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

async function unwrap<T>(result: Promise<Result<T>>): Promise<T> {
  const r = await result;
  if (!r.ok) throw new Error(r.error);
  return r.data;
}

export function notifyError(e: unknown) {
  toaster.toast({ title: "SSH Warden", body: e instanceof Error ? e.message : String(e) });
}

const getStatusCall = callable<[], Result<Status>>("get_status");
const setRunningCall = callable<[on: boolean], Result<null>>("set_running");
const setAutostartCall = callable<[on: boolean], Result<null>>("set_autostart");
const setAutooffCall = callable<[minutes: number], Result<null>>("set_autooff");

export const getStatus = () => unwrap(getStatusCall());
export const setRunning = (on: boolean) => unwrap(setRunningCall(on));
export const setAutostart = (on: boolean) => unwrap(setAutostartCall(on));
/** Stop SSH after `minutes`; 0 cancels. */
export const setAutooff = (minutes: number) => unwrap(setAutooffCall(minutes));

import { callable, toaster } from "@decky/api";
import { errorMessage } from "./i18n";

export interface Network {
  name: string;
  uuid: string;
  type: "wifi" | "ethernet";
  device: string;
  addresses: string[];
  zone: string | null;
  trusted: boolean;
  ssh_allowed: boolean;
}

export interface SavedNetwork {
  name: string;
  uuid: string;
  type: "wifi" | "ethernet";
  active: boolean;
  trusted: boolean;
}

export interface PublicKey {
  type: string;
  comment: string;
  fingerprint: string;
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
  /** Whether the deck user has a password; changing it then needs the current one. */
  password_set: boolean;
  keys: PublicKey[];
  /** Whether sshd lets these keys log in on their own, so password login may be turned off. */
  key_login: boolean;
  sessions: string[];
  logins: { recent: Login[]; failed: number };
  firewall: boolean;
  networks: Network[];
  trusted_mode: boolean;
  saved_networks: SavedNetwork[];
}

type Failure = { ok: false; error: string; code?: string; params?: Record<string, string | number> };
type Result<T> = { ok: true; data: T } | Failure;

async function unwrap<T>(result: Promise<Result<T>>): Promise<T> {
  const r = await result;
  if (!r.ok) throw new Error(errorMessage(r.code, r.params, r.error));
  return r.data;
}

export function notifyError(e: unknown) {
  toaster.toast({ title: "SSH Warden", body: e instanceof Error ? e.message : String(e) });
}

const getStatusCall = callable<[], Result<Status>>("get_status");
const setRunningCall = callable<[on: boolean], Result<null>>("set_running");
const setAutostartCall = callable<[on: boolean], Result<null>>("set_autostart");
const setAutooffCall = callable<[minutes: number], Result<null>>("set_autooff");
const setPortCall = callable<[port: number], Result<null>>("set_port");
const setPasswordAuthCall = callable<[on: boolean], Result<null>>("set_password_auth");
const changePasswordCall = callable<[currentPassword: string, newPassword: string], Result<null>>("change_password");
const importKeysCall = callable<[path: string], Result<{ added: number; skipped: number }>>("import_keys");
const removeKeyCall = callable<[fingerprint: string], Result<null>>("remove_key");
const setTrustedModeCall = callable<[on: boolean], Result<null>>("set_trusted_mode");
const setNetworkTrustedCall = callable<[uuid: string, on: boolean], Result<null>>("set_network_trusted");

export const getStatus = () => unwrap(getStatusCall());
export const setRunning = (on: boolean) => unwrap(setRunningCall(on));
export const setAutostart = (on: boolean) => unwrap(setAutostartCall(on));
/** Stop SSH after `minutes`; 0 cancels. */
export const setAutooff = (minutes: number) => unwrap(setAutooffCall(minutes));
export const setPort = (port: number) => unwrap(setPortCall(port));
export const setPasswordAuth = (on: boolean) => unwrap(setPasswordAuthCall(on));
export const changePassword = (currentPassword: string, newPassword: string) =>
  unwrap(changePasswordCall(currentPassword, newPassword));
/** Add the public keys found in a file on the Deck. */
export const importKeys = (path: string) => unwrap(importKeysCall(path));
export const removeKey = (fingerprint: string) => unwrap(removeKeyCall(fingerprint));
export const setTrustedMode = (on: boolean) => unwrap(setTrustedModeCall(on));
export const setNetworkTrusted = (uuid: string, on: boolean) => unwrap(setNetworkTrustedCall(uuid, on));

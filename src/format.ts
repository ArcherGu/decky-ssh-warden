const pad = (n: number) => String(n).padStart(2, "0");

/** Unix seconds -> "MM-DD HH:mm" in local time. */
export function formatTime(seconds: number) {
  const d = new Date(seconds * 1000);
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${formatClock(seconds)}`;
}

/** Unix seconds -> "HH:mm" in local time. */
export function formatClock(seconds: number) {
  const d = new Date(seconds * 1000);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Whole minutes from now until the given unix time (never negative). */
export function minutesUntil(seconds: number) {
  return Math.max(0, Math.ceil((seconds * 1000 - Date.now()) / 60000));
}

/** e.g. "ssh -p 2222 deck@192.168.1.5"; the port is left out when it is the default 22. */
export function sshCommand(program: "ssh" | "ssh-copy-id", user: string, address: string, port: number) {
  return `${program}${port === 22 ? "" : ` -p ${port}`} ${user}@${address}`;
}

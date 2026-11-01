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

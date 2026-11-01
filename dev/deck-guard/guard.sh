#!/bin/bash
# SSH Warden development guard.
#
# While the plugin is being developed and tested remotely, a bad test can leave the
# Steam Deck unreachable over SSH (sshd stopped, wrong port, firewall rule, changed
# password...). This guard runs every minute from a systemd timer. When the SSH-related
# state differs from the known-good baseline AND the developer has not touched the
# heartbeat file for STALE_SECONDS, it restores the baseline so SSH works again.
#
# Usage: guard.sh snapshot|check|rescue|status
set -u
# Fingerprints must not depend on the caller's locale (sort order, translated output).
export LC_ALL=C

STATE_DIR=/var/lib/ssh-warden-dev
BASE="$STATE_DIR/baseline"
HEARTBEAT=/home/deck/.ssh-warden-dev/heartbeat
STALE_SECONDS=${STALE_SECONDS:-300}
USER_NAME=deck
LOG="$STATE_DIR/guard.log"
COMPONENTS="sshd password firewall nm"

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

fp_sshd() {
  echo "active=$(systemctl is-active sshd.service) enabled=$(systemctl is-enabled sshd.service 2>&1)"
  sshd -T 2>&1 | grep -iE '^(port|listenaddress|passwordauthentication|pubkeyauthentication|permitrootlogin|allowusers|denyusers|allowgroups|denygroups|authenticationmethods|usepam) ' | sort
  ls -1 /etc/ssh/sshd_config.d
  sha256sum /etc/ssh/sshd_config
}

fp_password() {
  getent shadow "$USER_NAME" | cut -d: -f2 | sha256sum
}

fp_firewall() {
  firewall-cmd --state 2>&1
  firewall-cmd --get-default-zone
  firewall-cmd --list-all-zones
  firewall-cmd --permanent --list-all-zones
}

fp_nm() {
  nmcli -t -f UUID connection show | sort | while read -r uuid; do
    echo "$uuid zone=$(nmcli -g connection.zone connection show "$uuid" </dev/null)"
  done
}

hash_of() { "fp_$1" | sha256sum | cut -d' ' -f1; }

heartbeat_age() {
  local hb now
  hb=$(stat -c %Y "$HEARTBEAT" 2>/dev/null || echo 0)
  now=$(date +%s)
  echo $((now - hb))
}

changed_components() {
  local c out=""
  for c in $COMPONENTS; do
    [ "$(hash_of "$c")" = "$(cat "$BASE/$c.fp" 2>/dev/null)" ] || out="$out $c"
  done
  echo "${out# }"
}

snapshot() {
  if [ -d "$BASE" ] && [ "${1:-}" != "--force" ]; then
    echo "baseline already exists at $BASE (use --force to replace it)"
    return 0
  fi
  # Refuse to record a broken state as "known good".
  if [ "$(systemctl is-active sshd.service)" != active ] \
     || ! sshd -T | grep -qix 'port 22' \
     || ! sshd -T | grep -qix 'passwordauthentication yes'; then
    echo "current SSH state does not look healthy; not taking a snapshot" >&2
    return 1
  fi
  rm -rf "$BASE" && install -d -m 700 "$BASE"
  local c
  for c in $COMPONENTS; do
    "fp_$c" > "$BASE/$c.txt"   # human-readable copy, handy for diffing a mismatch
    hash_of "$c" > "$BASE/$c.fp"
  done
  cp -a /etc/ssh/sshd_config "$BASE/sshd_config"
  ls -1 /etc/ssh/sshd_config.d > "$BASE/sshd_config.d.list"
  getent shadow "$USER_NAME" | cut -d: -f2 > "$BASE/shadow-hash"
  tar -C /etc -cpf "$BASE/firewalld.tar" firewalld
  fp_nm > "$BASE/nm-zones.txt"
  chmod 600 "$BASE"/*
  log "baseline snapshot taken"
}

rescue_sshd() {
  local f
  systemctl stop ssh-warden-autooff.timer ssh-warden-autooff.service 2>/dev/null
  for f in /etc/ssh/sshd_config.d/*; do
    [ -e "$f" ] || [ -L "$f" ] || continue
    grep -qxF "$(basename "$f")" "$BASE/sshd_config.d.list" || { rm -f "$f"; log "removed $f"; }
  done
  cmp -s /etc/ssh/sshd_config "$BASE/sshd_config" || { cp -a "$BASE/sshd_config" /etc/ssh/sshd_config; log "restored sshd_config"; }
  systemctl unmask sshd.service 2>/dev/null
  systemctl enable sshd.service
  systemctl restart sshd.service
  log "sshd restarted: $(systemctl is-active sshd.service)"
}

rescue_password() {
  usermod -p "$(cat "$BASE/shadow-hash")" "$USER_NAME" && log "restored password hash for $USER_NAME"
}

rescue_firewall_and_nm() {
  local uuid zone dev
  rm -rf /etc/firewalld && tar -C /etc -xpf "$BASE/firewalld.tar" && log "restored /etc/firewalld"
  while read -r uuid zone; do
    zone=${zone#zone=}
    [ "$(nmcli -g connection.zone connection show "$uuid" 2>/dev/null </dev/null)" = "$zone" ] && continue
    nmcli connection modify "$uuid" connection.zone "$zone" </dev/null && log "reset zone of connection $uuid to '${zone}'"
  done < "$BASE/nm-zones.txt"
  if ! firewall-cmd --reload >/dev/null 2>&1; then
    log "firewall-cmd --reload failed, restarting firewalld"
    systemctl restart firewalld.service
  fi
  # Put every active Wi-Fi/Ethernet device back into the zone its connection asks for (or the
  # default zone). Other devices (loopback, VPN/proxy tun devices) are left alone on purpose.
  nmcli -t -f DEVICE,TYPE,UUID connection show --active | while IFS=: read -r dev type uuid; do
    case "$type" in 802-11-wireless|802-3-ethernet) ;; *) continue ;; esac
    [ -n "$dev" ] || continue
    zone=$(nmcli -g connection.zone connection show "$uuid" </dev/null)
    [ -n "$zone" ] || zone=$(firewall-cmd --get-default-zone </dev/null)
    firewall-cmd --zone="$zone" --change-interface="$dev" >/dev/null 2>&1 </dev/null
  done
  log "firewall reloaded"
}

rescue() {
  local changed="$1"
  log "RESCUE start (changed: $changed, heartbeat age: $(heartbeat_age)s)"
  case " $changed " in *" sshd "*) rescue_sshd ;; esac
  case " $changed " in *" password "*) rescue_password ;; esac
  case " $changed " in *" firewall "*|*" nm "*) rescue_firewall_and_nm ;; esac
  date '+%F %T' > "$STATE_DIR/last-rescue"
  log "RESCUE done, still changed: '$(changed_components)'"
}

check() {
  [ -d "$BASE" ] || { echo "no baseline, nothing to do"; return 0; }
  local changed age status
  changed=$(changed_components)
  age=$(heartbeat_age)
  if [ -z "$changed" ]; then
    status="baseline"
  elif [ "$age" -lt "$STALE_SECONDS" ]; then
    status="changed($changed),heartbeat-fresh"
  else
    status="rescue"
  fi
  # Only log when the status changes, so the journal stays readable.
  if [ "$status" != "$(cat "$STATE_DIR/last-status" 2>/dev/null)" ]; then
    log "status: $status (heartbeat age ${age}s)"
    echo "$status" > "$STATE_DIR/last-status"
  fi
  [ "$status" = rescue ] && rescue "$changed"
  return 0
}

status() {
  local c
  echo "heartbeat age: $(heartbeat_age)s (rescue after ${STALE_SECONDS}s)"
  echo "changed components: '$(changed_components)'"
  for c in $(changed_components); do
    [ -f "$BASE/$c.txt" ] && diff <(cat "$BASE/$c.txt") <("fp_$c") | sed "s/^/  [$c] /" | head -n 10
  done
  echo "last rescue: $(cat "$STATE_DIR/last-rescue" 2>/dev/null || echo never)"
  echo "timer: $(systemctl is-active ssh-warden-dev-guard.timer)"
  tail -n 5 "$LOG" 2>/dev/null
}

case "${1:-}" in
  snapshot) shift; snapshot "$@" ;;
  check) check ;;
  rescue) rescue "$(changed_components)" ;;
  status) status ;;
  *) echo "usage: $0 snapshot [--force]|check|rescue|status" >&2; exit 2 ;;
esac

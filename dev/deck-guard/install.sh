#!/bin/bash
# Install the SSH Warden development guard on the Steam Deck (run as root).
set -eu
cd "$(dirname "$0")"

STATE_DIR=/var/lib/ssh-warden-dev
install -d -m 700 "$STATE_DIR"
install -m 700 guard.sh "$STATE_DIR/guard.sh"
install -d -o deck -g deck /home/deck/.ssh-warden-dev
touch /home/deck/.ssh-warden-dev/heartbeat
chown deck:deck /home/deck/.ssh-warden-dev/heartbeat

"$STATE_DIR/guard.sh" snapshot "$@"

cat > /etc/systemd/system/ssh-warden-dev-guard.service <<'EOF'
[Unit]
Description=SSH Warden dev guard (restores SSH access if a remote test breaks it)
After=network-online.target sshd.service firewalld.service

[Service]
Type=oneshot
ExecStart=/var/lib/ssh-warden-dev/guard.sh check
EOF

cat > /etc/systemd/system/ssh-warden-dev-guard.timer <<'EOF'
[Unit]
Description=Run the SSH Warden dev guard every minute

[Timer]
OnBootSec=90s
OnUnitActiveSec=60s
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ssh-warden-dev-guard.timer
"$STATE_DIR/guard.sh" status

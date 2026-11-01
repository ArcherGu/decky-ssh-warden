#!/bin/bash
# Remove the SSH Warden development guard from the Steam Deck (run as root).
set -u
systemctl disable --now ssh-warden-dev-guard.timer 2>/dev/null
rm -f /etc/systemd/system/ssh-warden-dev-guard.timer /etc/systemd/system/ssh-warden-dev-guard.service
systemctl daemon-reload
# The state dir holds a copy of the deck user's password hash; do not leave it behind.
rm -rf /var/lib/ssh-warden-dev /home/deck/.ssh-warden-dev
echo "SSH Warden dev guard removed"

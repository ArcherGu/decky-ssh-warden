"""SSH Warden backend: manage sshd, the deck password and firewalld from a Decky plugin.

Everything here runs as root (the plugin has the "root" flag) and talks to the system
through its own CLI tools (systemctl, sshd, nmcli, firewall-cmd, ...).
"""

DECK_USER = "deck"

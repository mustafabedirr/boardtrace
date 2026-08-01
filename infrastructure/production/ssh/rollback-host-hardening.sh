#!/usr/bin/env bash
set -euo pipefail

# Run only from the still-open bootstrap session. This restores the packaged
# two-port key-only bootstrap policy; it never enables password or root authentication.
if [[ "${EUID}" -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi
readonly SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install -D -o root -g root -m 0644 \
  "$SOURCE_DIR/sshd_config.d/59-boardtrace-bootstrap.conf" \
  /etc/ssh/sshd_config.d/59-boardtrace-bootstrap.conf
rm -f /etc/ssh/sshd_config.d/60-boardtrace-production.conf
sshd -t
ufw allow 22/tcp comment 'Temporary BoardTrace rollback SSH'
ufw allow 48227/tcp comment 'BoardTrace SSH'
systemctl reload ssh
echo "Key-only ports 22 and 48227 restored. Inspect effective settings before closing sessions."

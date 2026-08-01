#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

readonly SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly MARKER=/run/boardtrace-second-session-verified

if [[ ! -f "$MARKER" || "$(stat -c '%U:%a' "$MARKER")" != "root:600" ]]; then
  echo "refusing finalization: root-owned second-session marker is absent" >&2
  exit 1
fi
if ! ss -Htn state established '( sport = :48227 )' | grep -q .; then
  echo "refusing finalization: no established SSH session on port 48227" >&2
  exit 1
fi

install -D -o root -g root -m 0644 \
  "$SOURCE_DIR/sshd_config.d/60-boardtrace-production.conf" \
  /etc/ssh/sshd_config.d/60-boardtrace-production.conf
rm -f /etc/ssh/sshd_config.d/59-boardtrace-bootstrap.conf

sshd -t
effective="$(sshd -T)"
grep -qx 'port 48227' <<<"$effective"
if grep -qx 'port 22' <<<"$effective"; then
  echo "refusing finalization: port 22 remains effective" >&2
  exit 1
fi
grep -qx 'permitrootlogin no' <<<"$effective"
grep -qx 'passwordauthentication no' <<<"$effective"
grep -qx 'kbdinteractiveauthentication no' <<<"$effective"
grep -qx 'pubkeyauthentication yes' <<<"$effective"

ufw allow 48227/tcp comment 'BoardTrace SSH'
ufw allow 80/tcp comment 'BoardTrace HTTP redirect'
ufw allow 443/tcp comment 'BoardTrace HTTPS'
ufw --force delete allow 22/tcp >/dev/null 2>&1 || true
ufw --force enable
systemctl reload ssh
rm -f "$MARKER"

echo "Final SSH policy loaded. Keep both administrative sessions open for verification."

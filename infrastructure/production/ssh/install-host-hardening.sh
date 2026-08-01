#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

readonly SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PRIMARY_USER="${BOARDTRACE_PRIMARY_ADMIN_USER:-mustafa}"
readonly SECONDARY_USER="${BOARDTRACE_SECONDARY_ADMIN_USER:-ahmet}"

for account in "$PRIMARY_USER" "$SECONDARY_USER"; do
  home_dir="$(getent passwd "$account" | cut -d: -f6)"
  key_file="$home_dir/.ssh/authorized_keys"
  if [[ -z "$home_dir" || ! -s "$key_file" ]]; then
    echo "refusing SSH change: $account lacks a non-empty authorized_keys file" >&2
    exit 1
  fi
done

install -D -o root -g root -m 0644 \
  "$SOURCE_DIR/sshd_config.d/59-boardtrace-bootstrap.conf" \
  /etc/ssh/sshd_config.d/59-boardtrace-bootstrap.conf
install -D -o root -g root -m 0644 \
  "$SOURCE_DIR/fail2ban/boardtrace-sshd.local" \
  /etc/fail2ban/jail.d/boardtrace-sshd.local
install -D -o root -g root -m 0755 \
  "$SOURCE_DIR/boardtrace-recovery" /usr/local/sbin/boardtrace-recovery
install -D -o root -g root -m 0440 \
  "$SOURCE_DIR/sudoers.d/boardtrace-secondary" /etc/sudoers.d/boardtrace-secondary

visudo -cf /etc/sudoers.d/boardtrace-secondary
sshd -t

effective="$(sshd -T)"
grep -qx 'port 22' <<<"$effective"
grep -qx 'port 48227' <<<"$effective"
grep -qx 'permitrootlogin no' <<<"$effective"
grep -qx 'passwordauthentication no' <<<"$effective"
grep -qx 'kbdinteractiveauthentication no' <<<"$effective"
grep -qx 'pubkeyauthentication yes' <<<"$effective"
grep -qx 'permitemptypasswords no' <<<"$effective"

ufw allow 48227/tcp comment 'BoardTrace SSH'
ufw allow 80/tcp comment 'BoardTrace HTTP redirect'
ufw allow 443/tcp comment 'BoardTrace HTTPS'
ufw allow 22/tcp comment 'Temporary BoardTrace bootstrap SSH'
ufw --force enable
systemctl enable --now fail2ban
systemctl reload ssh

echo "Bootstrap policy loaded; port 22 remains available."
echo "From a second key-authenticated port-48227 session, create the root marker:"
echo "  sudo install -o root -g root -m 0600 /dev/null /run/boardtrace-second-session-verified"
echo "Then run finalize-host-hardening.sh from the original open session."

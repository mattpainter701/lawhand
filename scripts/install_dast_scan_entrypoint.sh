#!/usr/bin/env bash
# Install the root-owned, argument-free DAST boundary used by prod-dast.yml.
# Run on the Skynet host: sudo bash scripts/install_dast_scan_entrypoint.sh
set -Eeuo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "Run with sudo" >&2; exit 2; }
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
runner_user="${RUNNER_USER:-lawhand-runner}"
entrypoint=/usr/local/sbin/lawhand-dast-scan
sudoers_file=/etc/sudoers.d/lawhand-dast-scan

id -u "$runner_user" >/dev/null 2>&1 || {
  echo "ERROR: runner account $runner_user does not exist" >&2
  exit 2
}
[[ -f "$script_dir/lawhand-dast-scan" ]] || {
  echo "ERROR: missing $script_dir/lawhand-dast-scan" >&2
  exit 2
}

install -m 0755 -o root -g root "$script_dir/lawhand-dast-scan" "$entrypoint"
printf '%s\n' "$runner_user ALL=(root) NOPASSWD: $entrypoint" >"$sudoers_file"
chmod 0440 "$sudoers_file"
visudo -cf "$sudoers_file"
echo "Installed $entrypoint and its exact-command sudo rule for $runner_user."

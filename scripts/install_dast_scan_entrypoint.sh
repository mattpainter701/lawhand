#!/usr/bin/env bash
# Install the root-owned, argument-free DAST boundaries used by prod-dast.yml:
# the passive OWASP ZAP baseline and the active Nuclei scan.
# Run on the Skynet host: sudo bash scripts/install_dast_scan_entrypoint.sh
set -Eeuo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "Run with sudo" >&2; exit 2; }
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
runner_user="${RUNNER_USER:-lawhand-runner}"
entrypoint=/usr/local/sbin/lawhand-dast-scan
active_entrypoint=/usr/local/sbin/lawhand-active-scan
sudoers_file=/etc/sudoers.d/lawhand-dast-scan

id -u "$runner_user" >/dev/null 2>&1 || {
  echo "ERROR: runner account $runner_user does not exist" >&2
  exit 2
}
for script in lawhand-dast-scan lawhand-active-scan; do
  [[ -f "$script_dir/$script" ]] || {
    echo "ERROR: missing $script_dir/$script" >&2
    exit 2
  }
done

install -m 0755 -o root -g root "$script_dir/lawhand-dast-scan" "$entrypoint"
install -m 0755 -o root -g root "$script_dir/lawhand-active-scan" "$active_entrypoint"
{
  printf '%s\n' "$runner_user ALL=(root) NOPASSWD: $entrypoint"
  printf '%s\n' "$runner_user ALL=(root) NOPASSWD: $active_entrypoint"
} >"$sudoers_file"
chmod 0440 "$sudoers_file"
visudo -cf "$sudoers_file"
echo "Installed $entrypoint and $active_entrypoint with exact-command sudo rules for $runner_user."


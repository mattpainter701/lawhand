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
  src="$script_dir/$script"
  [[ -f "$src" ]] || {
    echo "ERROR: missing $src" >&2
    exit 2
  }
  # install(1) copies bytes verbatim, so a CRLF checkout installs an entrypoint
  # whose shebang is `#!/usr/bin/env bash\r`. sudo then fails it with
  # `env: 'bash\r': No such file or directory` (exit 127) before a single line
  # runs, which reads downstream as "the scan produced no report" rather than
  # as a broken install. Refuse the source instead of shipping it.
  if LC_ALL=C grep -q $'\r' "$src"; then
    echo "ERROR: $src has CRLF line endings; re-checkout with LF" >&2
    exit 2
  fi
  bash -n "$src" || {
    echo "ERROR: $src is not valid bash" >&2
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


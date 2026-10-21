#!/usr/bin/env bash
# Run explicitly on the approved Ubuntu server. Does not publish the app or copy secrets.
# Docker installation follows https://docs.docker.com/engine/install/ubuntu/
set -euo pipefail

source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 24.04 ]]; then
  echo 'This deployment bootstrap expects Ubuntu 24.04 LTS.' >&2
  exit 1
fi

python3 - <<'PY'
import os, shutil
memory = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
if memory < 6 * 1024**3:
    raise SystemExit('At least 6 GiB of host memory is required for this deployment profile.')
if shutil.disk_usage('/').free < 15 * 1024**3:
    raise SystemExit('At least 15 GiB of free disk is required before the image build.')
print('Server memory and free disk passed deployment preflight.')
PY

sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
task_arch="$(dpkg --print-architecture)"
printf '%s\n' \
  'Types: deb' \
  'URIs: https://download.docker.com/linux/ubuntu' \
  "Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}" \
  'Components: stable' \
  "Architectures: $task_arch" \
  'Signed-By: /etc/apt/keyrings/docker.asc' \
  | sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null
sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker

sudo docker version --format '{{.Server.Version}}'
sudo docker compose version --short | python3 -c '
import re, sys
version = sys.stdin.read().strip()
numbers = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version)
if not numbers or tuple(map(int, numbers.groups())) < (2, 24, 4):
    raise SystemExit("Compose 2.24.4 or newer is required.")
print("Docker Compose ready: " + version)
'
task_project_dir="${1:-$HOME/patternworks}"
install -d -m 0700 "$task_project_dir"
echo 'Docker is ready. Transfer the source package and configure private server settings next.'

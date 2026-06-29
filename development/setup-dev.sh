#!/usr/bin/env bash
#
# setup-dev.sh — install the JAVV development toolchain on Ubuntu 24.04 (x86_64).
#
# Installs: build floor, Python (uv + ruff), Node 22 LTS (+ pyright), k8s tooling
# (kubectl, helm, k3d) and the scanners (trivy, grype). Idempotent: re-run any time;
# tools already present are skipped. Docker is assumed already installed.
#
# Does NOT install: MCP servers (see docs/research/TOOLING-AND-MCP.md) or OpenSearch
# (runs as a container in the dev cluster). See development/README.md.
#
# SUPPLY-CHAIN NOTE (AUDIT.md N7): several tools below install via `curl … | sh` from upstream
# (uv, helm, k3d, trivy, grype). That's an unpinned remote-script surface — acceptable for a
# local dev VM, NOT for CI. If any of these ever run in CI, switch to checksum-pinned downloads
# or distro packages. Pinned tool *versions* (gate tools) are set just below.
#
set -euo pipefail

# Gate-tool version pins (AUDIT.md I14) — these decide lint/type results, so they MUST
# match CI to keep local == CI. Bump here in one place. Scanners + k8s tooling intentionally
# track latest (security DBs / cluster compat are more defensible at HEAD). Once
# backend/pyproject.toml exists, prefer sourcing these from there / pre-commit pinned revs.
NODE_MAJOR=22
UV_VERSION=0.11.25
RUFF_VERSION=0.15.20
PYRIGHT_VERSION=1.1.411
PRE_COMMIT_VERSION=4.6.0

# --- helpers ----------------------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
skip() { printf '\033[1;32m  ✓\033[0m %s already present (%s)\n' "$1" "${2:-skipping}"; }
have() { command -v "$1" >/dev/null 2>&1; }

require_ubuntu() {
  if ! have apt-get; then
    echo "ERROR: this script targets Debian/Ubuntu (apt-get not found)." >&2
    exit 1
  fi
  if [ "$(uname -m)" != "x86_64" ]; then
    echo "WARNING: built for x86_64; on $(uname -m) the kubectl download arch may need adjusting." >&2
  fi
}

# --- 1. build floor + apt prerequisites -------------------------------------
install_build_floor() {
  log "Build floor + apt prerequisites"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y --no-install-recommends \
    build-essential \
    python3-venv python3-pip \
    ca-certificates curl gnupg unzip jq git
}

# --- 2. Python toolchain: uv (+ uvx) and ruff -------------------------------
install_uv() {
  if have uv; then skip uv "$(uv --version)"; return; fi
  log "Installing uv ${UV_VERSION} (Astral)"
  curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
  # uv installs to ~/.local/bin (or $CARGO_HOME); surface it for the rest of this run
  export PATH="$HOME/.local/bin:$PATH"
  have uv || { echo "ERROR: uv install did not land on PATH ($HOME/.local/bin)" >&2; exit 1; }
}

install_ruff() {
  if have ruff; then skip ruff "$(ruff --version)"; return; fi
  log "Installing ruff ${RUFF_VERSION} (uv tool install)"
  uv tool install "ruff==${RUFF_VERSION}"
}

# pre-commit (AUDIT.md N2): the local quality hooks. Installs the tool, then — if run from the
# repo root — wires the git hooks (pre-commit + commit-msg). Idempotent.
install_precommit() {
  if ! have pre-commit; then
    log "Installing pre-commit ${PRE_COMMIT_VERSION} (uv tool install)"
    uv tool install "pre-commit==${PRE_COMMIT_VERSION}"
  else
    skip pre-commit "$(pre-commit --version)"
  fi
  if [ -f .pre-commit-config.yaml ]; then
    log "Wiring git hooks (pre-commit + commit-msg)"
    pre-commit install --install-hooks >/dev/null
    pre-commit install --hook-type commit-msg >/dev/null
  else
    echo "  (run from the repo root to auto-install the git hooks: 'pre-commit install')" >&2
  fi
}

# --- 3. Node.js 22 LTS (+ npm/npx) and pyright ------------------------------
install_node() {
  if have node; then skip node "$(node --version)"; return; fi
  log "Installing Node.js ${NODE_MAJOR} LTS (NodeSource)"
  # ${SUDO:+...} adds 'sudo -E' only when non-root; as root $SUDO is empty so it's just 'bash -'
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | ${SUDO:+$SUDO -E} bash -
  $SUDO apt-get install -y nodejs
}

install_pyright() {
  if have pyright; then skip pyright "$(pyright --version)"; return; fi
  log "Installing pyright ${PYRIGHT_VERSION} (npm global)"
  $SUDO npm install -g "pyright@${PYRIGHT_VERSION}"
}

# --- 4. Kubernetes tooling: kubectl, helm, k3d ------------------------------
install_kubectl() {
  if have kubectl; then skip kubectl "$(kubectl version --client -o yaml 2>/dev/null | head -1)"; return; fi
  log "Installing kubectl (latest stable)"
  local ver; ver="$(curl -L -s https://dl.k8s.io/release/stable.txt)"
  curl -fsSLo /tmp/kubectl "https://dl.k8s.io/release/${ver}/bin/linux/amd64/kubectl"
  $SUDO install -m 0755 /tmp/kubectl /usr/local/bin/kubectl
  rm -f /tmp/kubectl
}

install_helm() {
  if have helm; then skip helm "$(helm version --short 2>/dev/null)"; return; fi
  log "Installing helm 3"
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | $SUDO bash
}

install_k3d() {
  if have k3d; then skip k3d "$(k3d version | head -1)"; return; fi
  log "Installing k3d (k3s-in-Docker)"
  curl -fsSL https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | $SUDO bash
}

# --- 5. Scanners: trivy, grype ----------------------------------------------
install_trivy() {
  if have trivy; then skip trivy "$(trivy --version | head -1)"; return; fi
  log "Installing trivy"
  curl -fsSL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
    | $SUDO sh -s -- -b /usr/local/bin
}

install_grype() {
  if have grype; then skip grype "$(grype version | head -1)"; return; fi
  log "Installing grype"
  curl -fsSL https://raw.githubusercontent.com/anchore/grype/main/install.sh \
    | $SUDO sh -s -- -b /usr/local/bin
}

# --- 6. GitHub CLI ----------------------------------------------------------
install_gh() {
  if have gh; then skip gh "$(gh --version | head -1)"; return; fi
  log "Installing GitHub CLI (gh)"
  $SUDO mkdir -p -m 755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | $SUDO tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
  $SUDO chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | $SUDO tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  $SUDO apt-get update -qq
  $SUDO apt-get install -y gh
}

# --- preflight: docker ------------------------------------------------------
check_docker() {
  if ! have docker; then
    echo "WARNING: docker not found. k3d needs the Docker daemon — install Docker first." >&2
    return
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "WARNING: docker is installed but 'docker info' failed. Start the daemon, and if it needs sudo," >&2
    echo "         add yourself to the docker group:  sudo usermod -aG docker \"\$USER\"  (then re-login)." >&2
  fi
}

# --- summary ----------------------------------------------------------------
# Not every tool accepts `--version` (helm/k3d/grype/kubectl use their own form).
tool_version() {
  case "$1" in
    helm)    helm version --short 2>/dev/null ;;
    k3d)     k3d version 2>/dev/null | head -1 ;;
    grype)   grype version 2>/dev/null | head -1 ;;
    kubectl) kubectl version --client 2>/dev/null | head -1 ;;
    *)       "$1" --version 2>/dev/null | head -1 ;;
  esac
}

summary() {
  log "Installed versions"
  export PATH="$HOME/.local/bin:$PATH"
  for t in docker uv ruff pre-commit node npm pyright kubectl helm k3d trivy grype gh; do
    if have "$t"; then
      printf '  %-9s %s\n' "$t" "$(tool_version "$t")"
    else
      printf '  %-9s MISSING\n' "$t"
    fi
  done
  cat <<'EOF'

Next steps:
  * If 'docker ps' needs sudo:  sudo usermod -aG docker "$USER"   (then re-login)
  * Ensure ~/.local/bin is on your PATH (uv installs there). Add to ~/.bashrc if missing:
        export PATH="$HOME/.local/bin:$PATH"
  * Stand up the local dev cluster + wire MCP servers — see development/README.md.
EOF
}

# --- run --------------------------------------------------------------------
main() {
  require_ubuntu
  install_build_floor
  install_uv
  install_ruff
  install_precommit
  install_node
  install_pyright
  install_kubectl
  install_helm
  install_k3d
  install_trivy
  install_grype
  install_gh
  check_docker
  summary
}

main "$@"

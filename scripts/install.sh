#!/bin/bash
# install.sh — localjev-spark on macOS or Linux (user service)
set -euo pipefail

export PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${LOCALJEV_HOME:-${HOME}/.localjev-spark}"
CONFIG_DIR="${HOME}/.config/localjev-spark"
CONFIG_FILE="${CONFIG_DIR}/localjev.env"
LOG_DIR="${HOME}/logs"
UNIT_NAME="localjev-spark"
MAC_LABEL="ai.localjev.spark"

mkdir -p "${HOME_DIR}" "${CONFIG_DIR}" "${LOG_DIR}"

if [ ! -f "${CONFIG_FILE}" ]; then
    cat > "${CONFIG_FILE}" <<'EOF'
LOCALJEV_BACKEND=laya
LOCALJEV_REPO=convaiinnovations/laya
# LOCALJEV_SUBFOLDER=
LOCALJEV_SPARK_HOSTS=spark-local,spark,localhost
LOCALJEV_SPARK_PORTS=8000,8001,8002
EOF
    echo "Wrote ${CONFIG_FILE}"
fi

# shellcheck disable=SC1090
set -a && source "${CONFIG_FILE}" && set +a

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -fsSL https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
fi

if [ ! -x "${HOME_DIR}/.venv/bin/python" ]; then
    uv venv --python 3.12 "${HOME_DIR}/.venv" || uv venv "${HOME_DIR}/.venv"
fi

export USE_TF=0
if [ -f "${ROOT}/pyproject.toml" ]; then
    uv pip install --python "${HOME_DIR}/.venv/bin/python" -e "${ROOT}[laya]"
else
    uv pip install --python "${HOME_DIR}/.venv/bin/python" \
        "localjev-spark[laya] @ git+https://github.com/rimusz/localjev-spark.git"
fi

BIN="${HOME_DIR}/.venv/bin/localjev-spark"
if [ ! -x "${BIN}" ]; then
    echo "localjev-spark binary missing after install" >&2
    exit 1
fi

uname_s="$(uname -s)"
if [ "${uname_s}" = "Darwin" ]; then
    PLIST="${HOME}/Library/LaunchAgents/${MAC_LABEL}.plist"
    mkdir -p "${HOME}/Library/LaunchAgents"
    # Retire older private-ai-stack names
    launchctl bootout "gui/$(id -u)/ai.localjev.sidecar" 2>/dev/null || true
    launchctl bootout "gui/$(id -u)/ai.laya.sidecar" 2>/dev/null || true
    rm -f "${HOME}/Library/LaunchAgents/ai.localjev.sidecar.plist" \
        "${HOME}/Library/LaunchAgents/ai.laya.sidecar.plist"
    cat > "${PLIST}" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${MAC_LABEL}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>${HOME_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>USE_TF</key>
    <string>0</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${HOME}/.local/bin</string>
    <key>LOCALJEV_BACKEND</key>
    <string>${LOCALJEV_BACKEND:-laya}</string>
    <key>LOCALJEV_REPO</key>
    <string>${LOCALJEV_REPO:-convaiinnovations/laya}</string>
    <key>LOCALJEV_SUBFOLDER</key>
    <string>${LOCALJEV_SUBFOLDER:-}</string>
    <key>LOCALJEV_SPARK_HOSTS</key>
    <string>${LOCALJEV_SPARK_HOSTS:-spark-local,spark,localhost}</string>
    <key>LOCALJEV_SPARK_PORTS</key>
    <string>${LOCALJEV_SPARK_PORTS:-8000,8001,8002}</string>
    <key>LOCALJEV_SPARK_UPSTREAM</key>
    <string>${LOCALJEV_SPARK_UPSTREAM:-}</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>${BIN}</string>
    <string>serve</string>
  </array>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/localjev-spark.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/localjev-spark.log</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)/${MAC_LABEL}" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "${PLIST}"
    launchctl kickstart -k "gui/$(id -u)/${MAC_LABEL}"
    echo "launchd ${MAC_LABEL} started"
elif [ "${uname_s}" = "Linux" ]; then
    UNIT_DIR="${HOME}/.config/systemd/user"
    mkdir -p "${UNIT_DIR}"
    cat > "${UNIT_DIR}/${UNIT_NAME}.service" << EOF
[Unit]
Description=localjev-spark judge + Spark chat proxy
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${HOME_DIR}
Environment=USE_TF=0
Environment=PATH=${HOME}/.local/bin:/usr/bin:/bin
Environment=LOCALJEV_BACKEND=${LOCALJEV_BACKEND:-laya}
Environment=LOCALJEV_REPO=${LOCALJEV_REPO:-convaiinnovations/laya}
Environment=LOCALJEV_SUBFOLDER=${LOCALJEV_SUBFOLDER:-}
Environment=LOCALJEV_SPARK_HOSTS=${LOCALJEV_SPARK_HOSTS:-spark-local,spark,localhost}
Environment=LOCALJEV_SPARK_PORTS=${LOCALJEV_SPARK_PORTS:-8000,8001,8002}
Environment=LOCALJEV_SPARK_UPSTREAM=${LOCALJEV_SPARK_UPSTREAM:-}
ExecStart=${BIN} serve
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now "${UNIT_NAME}.service"
    echo "systemd --user ${UNIT_NAME} started"
else
    echo "Unsupported OS ${uname_s}; run: ${BIN} serve" >&2
    exit 1
fi

echo "Waiting for :8090..."
ok=0
for _ in $(seq 1 90); do
    if curl -sf --connect-timeout 2 http://127.0.0.1:8090/health >/dev/null; then
        ok=1
        break
    fi
    sleep 2
done
if [ "${ok}" != "1" ]; then
    echo "Not healthy yet — check ${LOG_DIR}/localjev-spark.log" >&2
    exit 1
fi
curl -sf http://127.0.0.1:8090/health
echo
echo "localjev-spark ready"
echo "  Judge   http://127.0.0.1:8090/health"
echo "  Chat    http://127.0.0.1:8091/v1"

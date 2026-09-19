#!/bin/bash
# install.sh — localjev-spark on macOS or Linux (user service)
set -euo pipefail

export PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"

# Clone checkout, or empty when this file is piped into bash.
ROOT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
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
# LOCALJEV_BIND=127.0.0.1
LOCALJEV_SPARK_HOSTS=spark-local,spark,localhost
# Probe order — Spark has one live port. Pin with LOCALJEV_SPARK_UPSTREAM if you prefer.
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
if [ -n "${ROOT}" ] && [ -f "${ROOT}/pyproject.toml" ]; then
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

# User-global skills for Cursor, Claude, Codex, Grok (does not touch TypeSafe jev-auto / jev MCP).
copy_skills() {
    local src="$1"
    local tree
    for tree in .cursor .claude .agents .codex .grok; do
        if [ -d "${src}/${tree}/skills/localjev-spark" ]; then
            mkdir -p "${HOME}/${tree}/skills"
            rm -rf "${HOME}/${tree}/skills/localjev-spark" "${HOME}/${tree}/skills/localjev-auto"
            cp -R "${src}/${tree}/skills/localjev-spark" "${HOME}/${tree}/skills/"
            if [ -d "${src}/${tree}/skills/localjev-auto" ]; then
                cp -R "${src}/${tree}/skills/localjev-auto" "${HOME}/${tree}/skills/"
            fi
            echo "skills → ${HOME}/${tree}/skills/localjev-spark + localjev-auto"
        fi
    done
}
SKILL_SRC="${ROOT}"
if [ -z "${SKILL_SRC}" ] || [ ! -d "${SKILL_SRC}/.cursor/skills/localjev-spark" ]; then
    SKILL_TMP="$(mktemp -d "${TMPDIR:-/tmp}/localjev-spark-skills.XXXXXX")"
    git clone --depth 1 https://github.com/rimusz/localjev-spark.git "${SKILL_TMP}"
    SKILL_SRC="${SKILL_TMP}"
fi
copy_skills "${SKILL_SRC}"
if [ -n "${SKILL_TMP:-}" ]; then
    rm -rf "${SKILL_TMP}"
fi

uname_s="$(uname -s)"
if [ "${uname_s}" = "Darwin" ]; then
    PLIST="${HOME}/Library/LaunchAgents/${MAC_LABEL}.plist"
    mkdir -p "${HOME}/Library/LaunchAgents"
    # Retire older launchd labels if present
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
    <key>LOCALJEV_BIND</key>
    <string>${LOCALJEV_BIND:-0.0.0.0}</string>
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
    launchctl bootstrap "gui/$(id -u)" "${PLIST}" 2>/dev/null || true
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
Environment=LOCALJEV_BIND=${LOCALJEV_BIND:-0.0.0.0}
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

# Ports bind before Laya finishes loading. Judge is 200 only when loaded.
echo "Waiting for judge 200 and proxy up..."
ok=0
for _ in $(seq 1 150); do
    j_code="$(curl -s -o /tmp/localjev-judge.json -w "%{http_code}" --connect-timeout 2 http://127.0.0.1:8090/health || echo 000)"
    p_code="$(curl -s -o /tmp/localjev-proxy.json -w "%{http_code}" --connect-timeout 2 http://127.0.0.1:8091/health || echo 000)"
    if [ "${j_code}" = "200" ] && [ "${p_code}" = "200" ]; then
        ok=1
        break
    fi
    sleep 2
done
if [ "${ok}" != "1" ]; then
    echo "Not healthy yet — check ${LOG_DIR}/localjev-spark.log" >&2
    exit 1
fi
echo "Judge:"
cat /tmp/localjev-judge.json
echo
echo "Proxy:"
cat /tmp/localjev-proxy.json
echo
spark_url="$("${HOME_DIR}/.venv/bin/python" -c 'import json; print(json.load(open("/tmp/localjev-proxy.json")).get("spark") or "")' 2>/dev/null || true)"
if [ -z "${spark_url}" ]; then
    echo "⚠️  :8091 is up but no Spark slot answered — start Spark or set LOCALJEV_SPARK_UPSTREAM" >&2
else
    echo "Spark upstream ${spark_url}"
fi
echo "localjev-spark ready"
echo "  Judge   http://127.0.0.1:8090/health"
echo "  Chat    http://127.0.0.1:8091/v1"
echo
echo "Next"
echo "  1. Restart Grok / Codex / Cursor / Claude so skills load"
echo "  2. Add one extra model (keep your existing Spark / Grok / GPT rows):"
echo "       Base URL   http://127.0.0.1:8091/v1"
echo "       API key    not-needed"
echo "       Model id   spark-via-localjev"
echo "       Protocol   Chat Completions   (not :8090)"
echo "  3. Later:  ${BIN} status"

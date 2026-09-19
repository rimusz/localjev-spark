#!/bin/bash
# uninstall.sh — stop localjev-spark. Default keeps the venv. --purge deletes data + localjev skills.
set -euo pipefail

PURGE=0
if [ "${1:-}" = "--purge" ]; then
    PURGE=1
fi

HOME_DIR="${LOCALJEV_HOME:-${HOME}/.localjev-spark}"
CONFIG_DIR="${HOME}/.config/localjev-spark"
MAC_LABEL="ai.localjev.spark"
UNIT_NAME="localjev-spark"
BIN="${HOME_DIR}/.venv/bin/localjev-spark"

if [ -x "${BIN}" ]; then
    "${BIN}" uninstall ${PURGE:+--purge}
    exit $?
fi

# Fallback if the venv binary is already gone.
uname_s="$(uname -s)"
if [ "${uname_s}" = "Darwin" ]; then
    uid="$(id -u)"
    for label in "${MAC_LABEL}" ai.localjev.sidecar ai.laya.sidecar; do
        launchctl bootout "gui/${uid}/${label}" 2>/dev/null || true
        rm -f "${HOME}/Library/LaunchAgents/${label}.plist"
    done
    echo "stopped launchd ${MAC_LABEL}"
elif [ "${uname_s}" = "Linux" ]; then
    systemctl --user disable --now "${UNIT_NAME}.service" 2>/dev/null || true
    rm -f "${HOME}/.config/systemd/user/${UNIT_NAME}.service"
    systemctl --user daemon-reload 2>/dev/null || true
    echo "stopped systemd --user ${UNIT_NAME}"
fi

if [ "${PURGE}" != "1" ]; then
    echo "left ${HOME_DIR} (pass --purge to delete venv, config, and localjev skills)"
    exit 0
fi

rm -rf "${HOME_DIR}" "${CONFIG_DIR}"
rm -f "${HOME}/logs/localjev-spark.log"
for tree in .cursor .claude .agents .codex .grok; do
    rm -rf "${HOME}/${tree}/skills/localjev-spark" "${HOME}/${tree}/skills/localjev-auto"
done
echo "purged ${HOME_DIR}, ${CONFIG_DIR}, localjev skills (jev-auto / Jev MCP left alone)"

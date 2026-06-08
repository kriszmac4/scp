#!/usr/bin/env bash
# SCP — Session Context Pre-fill: Installer
# ==============================================
# Installs scp.py, configures Hermes, and sets up cron.
# Usage: bash setup.sh [profile] [hermes_home]

set -euo pipefail

SCP_DIR="$(cd "$(dirname "$0")" && pwd)"
SCP_SCRIPT="${SCP_DIR}/scp.py"
PROFILE="${1:-dev}"
HERMES_HOME="${2:-$HOME/.hermes}"
PROFILE_DIR="${HERMES_HOME}/profiles/${PROFILE}"
SCRIPTS_DIR="${PROFILE_DIR}/scripts"
OUTPUT_FILE="${PROFILE_DIR}/data/session_context.md"

echo "=== SCP — Session Context Pre-fill Installer ==="
echo "Profile:      ${PROFILE}"
echo "Hermes home:  ${HERMES_HOME}"
echo "Scripts dir:  ${SCRIPTS_DIR}"
echo ""

# --- Check prerequisites ---
if [ ! -f "${SCP_SCRIPT}" ]; then
    echo "❌ scp.py not found at ${SCP_SCRIPT}"
    echo "   Run this script from the SCP repo directory."
    exit 1
fi

if [ ! -d "${PROFILE_DIR}" ]; then
    echo "❌ Hermes profile directory not found: ${PROFILE_DIR}"
    echo "   Make sure the profile exists. Available profiles:"
    ls -1 "${HERMES_HOME}/profiles/" 2>/dev/null || echo "   (none)"
    exit 1
fi

# --- 1. Install script ---
echo "[1/4] Installing scp.py to ${SCRIPTS_DIR}..."
mkdir -p "${SCRIPTS_DIR}"
cp "${SCP_SCRIPT}" "${SCRIPTS_DIR}/scp.py"
chmod +x "${SCRIPTS_DIR}/scp.py"
echo "      ✓ scp.py installed"

# --- 2. Add prefill_messages_file to config.yaml ---
echo "[2/4] Configuring Hermes prefill_messages_file..."
CONFIG_FILE="${PROFILE_DIR}/config.yaml"

if [ ! -f "${CONFIG_FILE}" ]; then
    echo "      ! config.yaml not found at ${CONFIG_FILE}, creating..."
    touch "${CONFIG_FILE}"
fi

# Check if prefill_messages_file already exists
if grep -q "prefill_messages_file" "${CONFIG_FILE}" 2>/dev/null; then
    echo "      ✓ prefill_messages_file already configured in config.yaml"
else
    echo "" >> "${CONFIG_FILE}"
    echo "# SCP — Session Context Pre-fill (installed by scp setup.sh)" >> "${CONFIG_FILE}"
    echo "prefill_messages_file: '${OUTPUT_FILE}'" >> "${CONFIG_FILE}"
    echo "      ✓ Added to config.yaml: prefill_messages_file: ${OUTPUT_FILE}"
fi

# --- 3. Create output directory ---
echo "[3/4] Creating output directory..."
mkdir -p "$(dirname "${OUTPUT_FILE}")"
echo "      ✓ ${OUTPUT_FILE}"

# --- 4. Run initial generation ---
echo "[4/4] Running initial context generation..."
python3 "${SCRIPTS_DIR}/scp.py" --profile "${PROFILE}" --hermes-home "${HERMES_HOME}"
echo "      ✓ Context file generated"

echo ""
echo "=== ✅ SCP installed successfully ==="
echo ""
echo "Next steps:"
echo "  1. Add a cron job to refresh the context regularly:"
echo ""
echo "     hermes cron session-context-prefill --schedule \"every 1h\" --no-agent \\"
echo "        \"python3 ${SCRIPTS_DIR}/scp.py --profile ${PROFILE} --watchdog\""
echo ""
echo "     Or with system cron:"
echo "     0 * * * * python3 ${SCRIPTS_DIR}/scp.py --profile ${PROFILE} --watchdog"
echo ""
echo "  2. Start a NEW session (this config only applies to new sessions):"
echo "     hermes --profile ${PROFILE}"
echo ""
echo "  3. Verify the context is being injected:"
echo "     • The first message in every session now includes the SCP context"
echo "     • Run manually anytime: python3 ${SCRIPTS_DIR}/scp.py --profile ${PROFILE}"

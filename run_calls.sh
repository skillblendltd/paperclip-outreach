#!/bin/bash
# ============================================================
# VoySIQ — Autonomous Call Campaign Runner
# Schedule: 0 10 * * 1-5 (10am Mon-Fri UK time)
#
# Places outbound calls for campaigns with calling_enabled=True.
# Respects per-campaign daily limits and call gaps.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/venv/bin/python"
MANAGE="$SCRIPT_DIR/manage.py"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/calls_${TIMESTAMP}.log"

echo "=== Call Campaign Run: $(date) ===" | tee "$LOG_FILE"

# Place calls
$VENV "$MANAGE" place_calls 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"

# Analyze yesterday's calls and auto-improve script (delta mode)
echo "=== Analyzing calls & improving script ===" | tee -a "$LOG_FILE"
$VENV "$MANAGE" analyze_calls --apply 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "=== Completed: $(date) ===" | tee -a "$LOG_FILE"

# Keep last 30 days of logs
find "$LOG_DIR" -name 'calls_*.log' -mtime +30 -delete 2>/dev/null || true

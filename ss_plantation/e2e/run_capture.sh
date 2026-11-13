#!/bin/bash
# Captures the stills of the Indonesian process guide with the settings in credentials.env (KPM_SS_* entries).
#   ./run_capture.sh [out_dir]
set -uo pipefail
cd "$(dirname "$0")"
ENV_FILE="${CREDENTIALS_ENV:-/Volumes/ExStorage/git/credentials.env}"
get() { grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed "s/^['\"]//;s/['\"]$//"; }
export ODOO_URL="$(get KPM_SS_ODOO_URL)" API_URL="$(get KPM_SS_ODOO_URL)" ODOO_DB="$(get KPM_SS_ODOO_DB)"
export ODOO_LOGIN="$(get KPM_SS_ODOO_LOGIN)" ODOO_PW="$(get KPM_SS_ODOO_PASSWORD)" ODOO_API_KEY="$(get KPM_SS_ODOO_API_KEY)"
export E2E_COMPANY="$(get KPM_SS_E2E_COMPANY)"
exec python3 -u capture_guide.py "${1:-guide_out}"

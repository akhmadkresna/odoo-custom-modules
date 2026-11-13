#!/bin/bash
# Runs the offline field app browser test with the settings kept in ../../../credentials.env
# (the KPM_SS_* entries, the Odoo 20 plantation instance). No secrets live in this file.
#   ./run_offline.sh [out_dir]
set -euo pipefail
cd "$(dirname "$0")"
ENV_FILE="${CREDENTIALS_ENV:-/Volumes/ExStorage/git/credentials.env}"
get() { grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed "s/^['\"]//;s/['\"]$//"; }
export APP_HOST="$(get KPM_SS_APP_HOST)"
export APP_IP="$(get KPM_SS_APP_IP)"
export ODOO_DB="$(get KPM_SS_ODOO_DB)"
export ODOO_LOGIN="$(get KPM_SS_ODOO_LOGIN)"
export ODOO_PW="$(get KPM_SS_ODOO_PASSWORD)"
export ODOO_API_KEY="$(get KPM_SS_ODOO_API_KEY)"
export API_URL="$(get KPM_SS_ODOO_URL)"
export E2E_COMPANY="$(get KPM_SS_E2E_COMPANY)"
exec python3 -u offline_field.py "${1:-offline_out}"

#!/bin/bash
# Runs the Indonesian-interface browser test on the plantation instance with the settings in
# credentials.env (the KPM_SS_* entries), then removes the records the test created by hand.
#   ./run_ui.sh [out_dir]
set -uo pipefail
cd "$(dirname "$0")"
ENV_FILE="${CREDENTIALS_ENV:-/Volumes/ExStorage/git/credentials.env}"
get() { grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed "s/^['\"]//;s/['\"]$//"; }
export ODOO_URL="$(get KPM_SS_ODOO_URL)" API_URL="$(get KPM_SS_ODOO_URL)" ODOO_DB="$(get KPM_SS_ODOO_DB)"
export ODOO_LOGIN="$(get KPM_SS_ODOO_LOGIN)" ODOO_PW="$(get KPM_SS_ODOO_PASSWORD)" ODOO_API_KEY="$(get KPM_SS_ODOO_API_KEY)"
export E2E_COMPANY="$(get KPM_SS_E2E_COMPANY)" LANGMODE="${LANGMODE:-id}"
python3 cleanup_ui.py >/dev/null 2>&1   # leftovers from an interrupted run
python3 -u ui_plantation.py "${1:-ui_out}"; status=$?
python3 cleanup_ui.py
exit $status

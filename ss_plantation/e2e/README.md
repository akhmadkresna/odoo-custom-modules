# ss_plantation end-to-end test (JSON-2)

Runs the whole plantation flow against a dev server through the JSON-2 API, creating
master data when missing and then the transactions, calling the same buttons the UI calls.

    python3 e2e_plantation.py

Needs `KPM_DEV_ODOO_URL`, `KPM_DEV_ODOO_DB`, `KPM_DEV_ODOO_LOGIN` and `KPM_DEV_ODOO_API_KEY` in
`credentials.env` (path override: `KPM_CREDENTIALS=/path/to/file`). The API user must be in
company 2 and have the Plantation Manager group.

Flow: settings and warehouse, pay schemes, employee schemes, FFB prices, estate / blocks /
landmarks, fertiliser stock, activity, harvest tallies, transport note, three weigh tickets
(own estate, bought, sold), mill order with OER / KER, harvest pay, payslips, asset wizard,
yield report. Master data is idempotent; transactions are created on every run, so run it on
a dev database only.

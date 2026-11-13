{
    "name": "MCP Connector (ChatGPT / Claude)",
    "version": "17.0.1.0.0",
    "category": "Technical",
    "summary": "Expose Odoo to ChatGPT, Claude and other AI clients over MCP, with OAuth 2.1 and API keys",
    "description": """
Single-module MCP (Model Context Protocol) server for Odoo 17.

* ``POST /mcp`` - streamable-HTTP JSON-RPC endpoint (MCP 2025-06-18 / 2025-03-26 / 2024-11-05)
* ChatGPT-compatible ``search`` and ``fetch`` tools plus generic Odoo tools
* OAuth 2.1 (PKCE, dynamic client registration, refresh tokens) for ChatGPT and Claude connectors
* Static API keys with per-model Read/Create/Write/Delete scopes
* Everything runs as a real Odoo user, so access rights and record rules always apply
* Audit log of every tool call
""",
    "author": "Local",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/api_key_views.xml",
        "views/oauth_views.xml",
        "views/audit_log_views.xml",
        "views/menu.xml",
        "templates/oauth_templates.xml",
    ],
    "installable": True,
    "application": False,
}

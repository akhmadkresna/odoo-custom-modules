"""Who is calling the MCP endpoint, and what are they allowed to touch."""

# Models that are never exposed, whoever calls (secrets, auth, config).
BLOCKED_MODELS = {
    "ir.config_parameter",
    "ir.cron",
    "ir.rule",
    "ir.model.access",
    "ir.mail_server",
    "ir.attachment",
    "res.users.apikeys",
    "res.users.apikeys.description",
    "res.users.log",
    "res.device",
    "res.device.log",
    "auth.totp.device",
    "base.automation",
}
BLOCKED_PREFIXES = ("mcp.", "bus.", "auth_", "ir.actions.server")

PERMS = ("read", "create", "write", "unlink")


def is_blocked(model_name):
    return model_name in BLOCKED_MODELS or model_name.startswith(BLOCKED_PREFIXES)


class Principal:
    """An authenticated caller: an Odoo user plus the credential's own limits."""

    def __init__(self, user, source, key=None, client=None):
        self.user = user
        self.source = source  # "api_key" | "oauth"
        self.key = key
        self.client = client

    def can(self, model_name, perm):
        """Credential-level check (Odoo ACLs are enforced separately by the ORM)."""
        if is_blocked(model_name):
            return False
        if self.source == "api_key":
            lines = self.key.sudo().access_ids.filtered(
                lambda l: l.model_name == model_name
            )
            return any(l["perm_" + perm] for l in lines)
        # OAuth: read always, create/write if the client allows it, never delete.
        if perm == "read":
            return True
        if perm in ("create", "write"):
            return bool(self.client.sudo().allow_write)
        return False

    @property
    def label(self):
        if self.source == "api_key":
            return "key:%s" % self.key.sudo().name
        return "oauth:%s" % self.client.sudo().name

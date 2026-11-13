"""MCP tools. Each handler takes (ctx, args) and returns a JSON-serialisable value."""
import json

from odoo.addons.mcp_odoo_connector.models.principal import is_blocked

MAX_LIMIT = 200
DEFAULT_SEARCH_MODELS = (
    "res.partner,product.template,sale.order,purchase.order,account.move,"
    "crm.lead,project.task,stock.picking,hr.employee"
)
SKIP_FIELD_PREFIXES = ("message_", "activity_", "website_message", "__")


class ToolError(Exception):
    """A problem the AI client should see and can react to."""


class Ctx:
    def __init__(self, env, principal):
        self.env = env
        self.principal = principal

    def model(self, name, perm):
        if not isinstance(name, str) or name not in self.env:
            raise ToolError("Unknown model: %r" % (name,))
        if is_blocked(name):
            raise ToolError("Model %s is not exposed over MCP." % name)
        if not self.principal.can(name, perm):
            raise ToolError("This credential has no %s access to %s." % (perm, name))
        return self.env[name]

    def base_url(self):
        return (self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")

    def record_url(self, model, rid):
        return "%s/web#id=%s&model=%s&view_type=form" % (self.base_url(), rid, model)


def _int(v, default, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _domain(v):
    if v in (None, "", []):
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            raise ToolError("domain must be a JSON list, e.g. [[\"name\",\"ilike\",\"x\"]]")
    if not isinstance(v, list):
        raise ToolError("domain must be a list")
    return v


def _ids(v):
    if isinstance(v, int):
        v = [v]
    if not isinstance(v, list) or not v or not all(isinstance(i, int) for i in v):
        raise ToolError("ids must be a non-empty list of integers")
    if len(v) > MAX_LIMIT:
        raise ToolError("At most %d ids per call" % MAX_LIMIT)
    return v


def _values(v):
    if not isinstance(v, dict) or not v:
        raise ToolError("values must be a non-empty object of field: value")
    return v


# --------------------------------------------------------------------------- ChatGPT


def tool_search(ctx, args):
    query = (args.get("query") or "").strip()
    if not query:
        raise ToolError("query is required")
    names = ctx.env["ir.config_parameter"].sudo().get_param(
        "mcp_odoo_connector.search_models", DEFAULT_SEARCH_MODELS)
    results = []
    for name in [n.strip() for n in names.split(",") if n.strip()]:
        if name not in ctx.env or is_blocked(name) or not ctx.principal.can(name, "read"):
            continue
        model = ctx.env[name]
        if not model.check_access_rights("read", raise_exception=False):
            continue
        for rid, label in model.name_search(query, limit=5):
            results.append({
                "id": "%s:%s" % (name, rid),
                "title": "%s (%s)" % (label, model._description or name),
                "url": ctx.record_url(name, rid),
            })
    return {"results": results[:25]}


def _fetch_fields(model):
    out = []
    for fname, f in model._fields.items():
        if not f.store or f.type in ("binary", "image") or fname.startswith(SKIP_FIELD_PREFIXES):
            continue
        out.append(fname)
    return out


def tool_fetch(ctx, args):
    rid = str(args.get("id") or "")
    name, _, num = rid.partition(":")
    if not num.isdigit():
        raise ToolError("id must look like 'res.partner:42' (as returned by search)")
    model = ctx.model(name, "read")
    rec = model.browse(int(num)).exists()
    if not rec:
        raise ToolError("Record not found: %s" % rid)
    rec.check_access_rule("read")
    fields_ = _fetch_fields(model)
    allowed = []
    for f in fields_:  # skip fields the user's groups hide instead of failing
        try:
            rec.read([f])
            allowed.append(f)
        except Exception:
            continue
    data = rec.read(allowed)[0]
    lines = []
    for k, v in data.items():
        if v in (False, None, [], ""):
            continue
        if isinstance(v, tuple):
            v = v[1]
        lines.append("%s: %s" % (model._fields[k].string or k, v))
    return {
        "id": rid,
        "title": rec.display_name,
        "text": "\n".join(lines),
        "url": ctx.record_url(name, rec.id),
        "metadata": {"model": name, "record_id": rec.id},
    }


# --------------------------------------------------------------------------- generic


def tool_list_models(ctx, args):
    query = (args.get("query") or "").strip().lower()
    limit = _int(args.get("limit"), 50, 1, 200)
    out = []
    for m in ctx.env["ir.model"].sudo().search([("transient", "=", False)], order="model"):
        if query and query not in m.model.lower() and query not in (m.name or "").lower():
            continue
        if m.model not in ctx.env or not ctx.principal.can(m.model, "read"):
            continue
        if not ctx.env[m.model].check_access_rights("read", raise_exception=False):
            continue
        out.append({"model": m.model, "name": m.name})
        if len(out) >= limit:
            break
    return {"models": out}


def tool_describe_model(ctx, args):
    model = ctx.model(args.get("model"), "read")
    info = model.fields_get(attributes=[
        "string", "type", "required", "readonly", "relation", "selection", "store"])
    return {"model": model._name, "description": model._description, "fields": info}


def tool_search_read(ctx, args):
    model = ctx.model(args.get("model"), "read")
    fields_ = args.get("fields") or ["display_name"]
    if not isinstance(fields_, list):
        raise ToolError("fields must be a list of field names")
    limit = _int(args.get("limit"), 20, 1, MAX_LIMIT)
    offset = _int(args.get("offset"), 0, 0, 10 ** 9)
    domain = _domain(args.get("domain"))
    rows = model.search_read(domain, fields_, limit=limit, offset=offset, order=args.get("order") or None)
    return {"count": model.search_count(domain), "records": rows}


def tool_read_group(ctx, args):
    model = ctx.model(args.get("model"), "read")
    groupby = args.get("groupby") or []
    fields_ = args.get("fields") or []
    if not isinstance(groupby, list) or not groupby or not isinstance(fields_, list):
        raise ToolError("groupby (list) is required; fields is a list like ['amount_total:sum']")
    rows = model.read_group(
        _domain(args.get("domain")), fields_, groupby,
        limit=_int(args.get("limit"), 50, 1, MAX_LIMIT),
        orderby=args.get("orderby") or False, lazy=False)
    return {"groups": rows}


def tool_create(ctx, args):
    model = ctx.model(args.get("model"), "create")
    rec = model.create(_values(args.get("values")))
    return {"id": rec.id, "display_name": rec.display_name, "url": ctx.record_url(model._name, rec.id)}


def tool_write(ctx, args):
    model = ctx.model(args.get("model"), "write")
    recs = model.browse(_ids(args.get("ids"))).exists()
    recs.write(_values(args.get("values")))
    return {"updated": recs.ids}


def tool_delete(ctx, args):
    model = ctx.model(args.get("model"), "unlink")
    recs = model.browse(_ids(args.get("ids"))).exists()
    deleted = recs.ids
    recs.unlink()
    return {"deleted": deleted}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


_MODEL = {"type": "string", "description": "Technical model name, e.g. res.partner"}
_DOMAIN = {"type": "array", "description": "Odoo domain, e.g. [[\"state\",\"=\",\"sale\"]]", "items": {}}
_VALUES = {"type": "object", "description": "Field values, e.g. {\"name\": \"ACME\"}"}
_IDS = {"type": "array", "items": {"type": "integer"}}

TOOLS = [
    ("search", tool_search, "Search Odoo records by text (partners, products, orders, invoices, leads, ...). "
     "Returns ids to pass to fetch.", _schema({"query": {"type": "string"}}, ["query"]), True),
    ("fetch", tool_fetch, "Fetch one Odoo record by the id returned from search (e.g. 'res.partner:42').",
     _schema({"id": {"type": "string"}}, ["id"]), True),
    ("odoo_list_models", tool_list_models, "List Odoo models you can read, optionally filtered by text.",
     _schema({"query": {"type": "string"}, "limit": {"type": "integer"}}), True),
    ("odoo_describe_model", tool_describe_model, "Describe the fields of an Odoo model.",
     _schema({"model": _MODEL}, ["model"]), True),
    ("odoo_search_read", tool_search_read, "Search and read records of a model (max 200 per call).",
     _schema({"model": _MODEL, "domain": _DOMAIN, "fields": {"type": "array", "items": {"type": "string"}},
              "limit": {"type": "integer"}, "offset": {"type": "integer"}, "order": {"type": "string"}},
             ["model"]), True),
    ("odoo_read_group", tool_read_group, "Aggregate records, e.g. fields ['amount_total:sum'], groupby ['partner_id'].",
     _schema({"model": _MODEL, "domain": _DOMAIN, "fields": {"type": "array", "items": {"type": "string"}},
              "groupby": {"type": "array", "items": {"type": "string"}},
              "limit": {"type": "integer"}, "orderby": {"type": "string"}}, ["model", "groupby"]), True),
    ("odoo_create", tool_create, "Create a record.", _schema({"model": _MODEL, "values": _VALUES},
                                                           ["model", "values"]), False),
    ("odoo_write", tool_write, "Update existing records.", _schema({"model": _MODEL, "ids": _IDS, "values": _VALUES},
                                                                  ["model", "ids", "values"]), False),
    ("odoo_delete", tool_delete, "Delete records (API keys with Delete permission only).",
     _schema({"model": _MODEL, "ids": _IDS}, ["model", "ids"]), False),
]

HANDLERS = {name: fn for name, fn, *_ in TOOLS}


def tool_definitions():
    return [{
        "name": name,
        "description": desc,
        "inputSchema": schema,
        "annotations": {"readOnlyHint": read_only, "destructiveHint": name == "odoo_delete",
                        "openWorldHint": False},
    } for name, _fn, desc, schema, read_only in TOOLS]

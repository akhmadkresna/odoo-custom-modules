import json
import logging
import time

from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

from odoo.addons.mcp_odoo_connector.models.principal import Principal
from . import tools

_logger = logging.getLogger(__name__)

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "authorization, content-type, mcp-protocol-version, mcp-session-id",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Expose-Headers": "WWW-Authenticate",
}


def _rpc_error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


class McpController(http.Controller):

    # ---- helpers
    def _response(self, body=None, status=200, headers=None):
        data = json.dumps(body, default=str) if body is not None else ""
        resp = request.make_response(data, headers=[("Content-Type", "application/json")])
        resp.status_code = status
        for k, v in {**CORS, **(headers or {})}.items():
            resp.headers[k] = v
        return resp

    def _unauthorized(self):
        base = (request.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")
        return self._response(
            _rpc_error(None, -32001, "Unauthorized"), 401,
            {"WWW-Authenticate": 'Bearer resource_metadata="%s/.well-known/oauth-protected-resource"' % base})

    def _authenticate(self):
        auth = request.httprequest.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        token = auth[7:].strip()
        ip = request.httprequest.remote_addr
        token_rec = request.env["mcp.oauth.token"].resolve_access(token, ip)
        if token_rec:
            return Principal(token_rec.user_id, "oauth", client=token_rec.client_id)
        key = request.env["mcp.api.key"].resolve(token, ip)
        if key:
            return Principal(key.user_id, "api_key", key=key)
        return None

    # ---- endpoint
    @http.route("/mcp", type="http", auth="public", methods=["POST", "GET", "DELETE", "OPTIONS"],
                csrf=False, save_session=False)
    def mcp(self, **kwargs):
        method = request.httprequest.method
        if method == "OPTIONS":
            return self._response(status=204)
        principal = self._authenticate()
        if not principal:
            return self._unauthorized()
        if method != "POST":  # no server-initiated stream / sessions
            return self._response(status=405, headers={"Allow": "POST, OPTIONS"})
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "")
        except ValueError:
            return self._response(_rpc_error(None, -32700, "Parse error"), 400)

        env = request.env(user=principal.user.id)
        batch = isinstance(payload, list)
        outputs = []
        for msg in (payload if batch else [payload]):
            out = self._dispatch(env, principal, msg)
            if out is not None:
                outputs.append(out)
        if not outputs:  # only notifications / responses
            return self._response(status=202)
        return self._response(outputs if batch else outputs[0])

    def _dispatch(self, env, principal, msg):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _rpc_error(None, -32600, "Invalid request")
        rid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if "method" not in msg or rid is None:
            return None  # notification or client response
        try:
            if method == "initialize":
                wanted = params.get("protocolVersion")
                version = wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                result = {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "odoo-mcp-connector", "version": "17.0.1.0.0"},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": tools.tool_definitions()}
            elif method == "tools/call":
                result = self._call_tool(env, principal, params)
            else:
                return _rpc_error(rid, -32601, "Method not found: %s" % method)
        except Exception:  # noqa: BLE001
            _logger.exception("MCP dispatch failed")
            return _rpc_error(rid, -32603, "Internal error")
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def _call_tool(self, env, principal, params):
        name, args = params.get("name"), params.get("arguments") or {}
        handler = tools.HANDLERS.get(name)
        started = time.monotonic()
        status, message, payload = "ok", "", None
        if not handler or not isinstance(args, dict):
            status, message = "error", "Unknown tool or bad arguments"
        else:
            try:
                with env.cr.savepoint():
                    payload = handler(tools.Ctx(env, principal), args)
            except tools.ToolError as e:
                status, message = "denied", str(e)
            except AccessError as e:
                status, message = "denied", str(e)
            except (UserError, ValidationError, MissingError) as e:
                status, message = "error", str(e)
            except Exception as e:  # noqa: BLE001
                _logger.exception("MCP tool %s failed", name)
                status, message = "error", "Internal error (%s)" % type(e).__name__
        self._audit(principal, name, args, status, message, started)
        if status == "ok":
            return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}
        return {"isError": True, "content": [{"type": "text", "text": message}]}

    def _audit(self, principal, tool, args, status, message, started):
        model = args.get("model") if isinstance(args, dict) else None
        request.env["mcp.audit.log"].sudo().create({
            "user_id": principal.user.id,
            "source": principal.source,
            "credential": principal.label,
            "tool": str(tool)[:64],
            "model_name": model if isinstance(model, str) else False,
            "status": status,
            "message": message,
            "arguments": json.dumps(args, default=str)[:2000],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "ip": request.httprequest.remote_addr,
        })

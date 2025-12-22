from __future__ import annotations

import os
import datetime
from typing import Any, Dict

from flask import Blueprint, Response, jsonify, session, current_app

bp = Blueprint("debug_admin", __name__, url_prefix="/admin")


def _is_admin() -> bool:
        return bool(session.get("is_admin")) or os.environ.get("FLASK_ENV") == "development"


def _probe(path: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {"path": path}
        try:
                c = current_app.test_client()
                resp = c.get(path)
                out["status"] = resp.status_code
                out["content_type"] = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
                body = resp.get_data(as_text=True) or ""
                body = body.replace("\r", "")
                out["snippet"] = body[:400] + ("…" if len(body) > 400 else "")
        except Exception as e:
                out["status"] = None
                out["content_type"] = None
                out["snippet"] = f"probe_error: {e}"
        return out


def _build_report() -> Dict[str, Any]:
        now = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        return {
                "ok": True,
                "utc": now,
                "is_admin": _is_admin(),
                "env": {
                        "UPLOADS_ROOT": current_app.config.get("UPLOADS_ROOT"),
                        "MEDIA_ROOT": current_app.config.get("MEDIA_ROOT"),
                        "MEDIA_URL": current_app.config.get("MEDIA_URL"),
                        "CLOUDINARY_URL_set": bool(os.environ.get("CLOUDINARY_URL")),
                        "DATABASE_URL_set": bool(os.environ.get("DATABASE_URL")),
                },
                "checks": [
                        _probe("/api/market/ping"),
                        _probe("/api/market/my/items?page=1"),
                        _probe("/api/lang/me"),
                        _probe("/api/suggestions"),
                ],
        }


@bp.get("/debug")
def debug_page() -> Response:
        r = _build_report()
        rows = []
        for c in r["checks"]:
                rows.append(
                        f"<tr><td><code>{c['path']}</code></td>"
                        f"<td>{c.get('status')}</td>"
                        f"<td><code>{c.get('content_type','')}</code></td>"
                        f"<td><code>{(c.get('snippet','') or '').replace('<','&lt;')}</code></td></tr>"
                )
        html = f"""
        <html><head><meta charset="utf-8"><title>Admin Debug</title></head>
        <body style="font-family:system-ui;background:#0b1020;color:#e8ecff;padding:24px">
          <h1>Admin Debug</h1>
          <p>UTC: <code>{r['utc']}</code> · admin: <b>{r['is_admin']}</b></p>
          <p><a style="color:#8ab4ff" href="/admin/debug/report.json">Open JSON report</a></p>
          <table border="1" cellpadding="8" cellspacing="0" style="border-color:#2b355a">
                <thead><tr><th>Path</th><th>Status</th><th>Content-Type</th><th>Snippet</th></tr></thead>
                <tbody>{''.join(rows)}</tbody>
          </table>
        </body></html>
        """
        return Response(html, mimetype="text/html")


@bp.get("/debug/report.json")
def debug_report() -> Response:
        if not _is_admin():
                return jsonify({"ok": False, "error": "forbidden"}), 403
        return jsonify(_build_report())
def _route_exists(rule: str) -> bool:
        try:
                for r in current_app.url_map.iter_rules():
                        if r.rule == rule:
                                return True
                return False
        except Exception:
                return False


def _probe(path: str) -> Dict[str, Any]:
        """
        Internal probe using Flask test_client to avoid external HTTP.
        Returns status, content-type, and a short body snippet.
        """
        out: Dict[str, Any] = {"path": path}
        try:
                c = current_app.test_client()
                resp = c.get(path)
                out["status"] = resp.status_code
                out["content_type"] = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
                body = resp.get_data(as_text=True) or ""
                body = body.replace("\r", "")
                out["snippet"] = (body[:400] + ("…" if len(body) > 400 else ""))
        except Exception as e:
                out["status"] = None
                out["content_type"] = None
                out["snippet"] = f"probe_error: {e}"
        return out


def _build_report() -> Dict[str, Any]:
        now = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        env = {
                "FLASK_ENV": os.environ.get("FLASK_ENV"),
                "UPLOADS_ROOT": current_app.config.get("UPLOADS_ROOT"),
                "MEDIA_ROOT": current_app.config.get("MEDIA_ROOT"),
                "MEDIA_URL": current_app.config.get("MEDIA_URL"),
                "CLOUDINARY_URL_set": bool(os.environ.get("CLOUDINARY_URL")),
                "DATABASE_URL_set": bool(os.environ.get("DATABASE_URL")),
        }

        must_routes = [
                "/admin/debug",
                "/admin/debug/report.json",
                "/api/market/ping",
                "/api/market/my/items",
                "/api/market/media/<path:filename>",
                "/media/<path:filename>",
                "/api/lang/me",
        ]
        routes = {r: _route_exists(r) for r in must_routes}

        checks: List[Dict[str, Any]] = [
                _probe("/api/market/ping"),
                _probe("/api/market/my/items?page=1"),
                _probe("/api/lang/me"),
                _probe("/api/suggestions"),  # якщо нема — буде 404 і це ок, але debug покаже
        ]

        return {
                "ok": True,
                "utc": now,
                "is_admin": _is_admin(),
                "env": env,
                "routes_present": routes,
                "checks": checks,
        }


@bp.get("/debug")
def debug_page() -> Response:
        report = _build_report()

        # Minimal CSS (no external assets)
        css = """
        :root{color-scheme:dark}
        body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;background:#070b14;color:#e8ecff}
        .wrap{max-width:1100px;margin:40px auto;padding:0 18px}
        .card{background:linear-gradient(180deg,#111a33,#0c1226);border:1px solid rgba(255,255,255,.08);border-radius:18px;padding:22px;box-shadow:0 20px 60px rgba(0,0,0,.45)}
        h1{margin:0 0 10px;font-size:42px;letter-spacing:.4px}
        .sub{opacity:.85;margin:0 0 18px}
        .row{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 18px}
        .pill{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.08)}
        .ok{color:#39d98a}
        .bad{color:#ff5c77}
        .btn{cursor:pointer;user-select:none;padding:10px 14px;border-radius:12px;background:rgba(116,161,255,.18);border:1px solid rgba(116,161,255,.25);color:#dbe7ff}
        .btn:hover{background:rgba(116,161,255,.28)}
        table{width:100%;border-collapse:separate;border-spacing:0;overflow:hidden;border-radius:14px;border:1px solid rgba(255,255,255,.08)}
        th,td{padding:12px 12px;border-bottom:1px solid rgba(255,255,255,.06);vertical-align:top}
        th{background:rgba(255,255,255,.04);text-align:left;font-weight:650}
        tr:last-child td{border-bottom:none}
        code{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12px}
        .muted{opacity:.75}
        """

        checks_rows = []
        for c in report.get("checks", []):
                status = c.get("status")
                cls = "ok" if status and 200 <= int(status) < 300 else "bad"
                checks_rows.append(f"""
                    <tr>
                        <td><code>{c.get('path','')}</code></td>
                        <td class="{cls}"><b>{status}</b></td>
                        <td class="muted"><code>{c.get('content_type','')}</code></td>
                        <td><code>{(c.get('snippet','') or '').replace('<','&lt;')}</code></td>
                    </tr>
                """)

        routes_rows = []
        for k, v in (report.get("routes_present") or {}).items():
                cls = "ok" if v else "bad"
                routes_rows.append(f"""
                    <tr>
                        <td><code>{k}</code></td>
                        <td class="{cls}"><b>{'YES' if v else 'NO'}</b></td>
                    </tr>
                """)

        html = f"""
        <html><head><meta charset="utf-8"/><title>Admin Debug</title><style>{css}</style></head>
        <body>
            <div class="wrap">
                <div class="card">
                    <h1>Admin Debug</h1>
                    <p class="sub">UTC: <code>{report.get('utc')}</code> · admin: <b class="{'ok' if report.get('is_admin') else 'bad'}">{report.get('is_admin')}</b></p>

                    <div class="row">
                        <span class="pill"><span class="ok">●</span> debug_admin loaded</span>
                        <button class="btn" id="open-json">Open JSON report</button>
                        <button class="btn" id="copy-json">Copy JSON</button>
                    </div>

                    <h3 style="margin:18px 0 10px">Health checks</h3>
                    <table>
                        <thead><tr><th>Path</th><th>Status</th><th>Content-Type</th><th>Snippet</th></tr></thead>
                        <tbody>
                            {''.join(checks_rows)}
                        </tbody>
                    </table>

                    <h3 style="margin:22px 0 10px">Critical routes presence</h3>
                    <table>
                        <thead><tr><th>Route</th><th>Present</th></tr></thead>
                        <tbody>
                            {''.join(routes_rows)}
                        </tbody>
                    </table>

                    <h3 style="margin:22px 0 10px">ENV summary</h3>
                    <pre style="margin:0;padding:14px;border-radius:14px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08)"><code>{jsonify(report.get('env')).get_data(as_text=True).strip()}</code></pre>
                </div>
            </div>

            <script>
                const reportUrl = "/admin/debug/report.json";
                const report = {jsonify(report).get_data(as_text=True)};
                document.getElementById("open-json").onclick = () => window.open(reportUrl, "_blank");
                document.getElementById("copy-json").onclick = async () => {{
                    await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
                    alert("Copied JSON ✅");
                }};
            </script>
        </body></html>
        """
        return Response(html, mimetype="text/html")


@bp.get("/debug/report.json")
def debug_report() -> Response:
        if not _is_admin():
                return jsonify({"ok": False, "error": "forbidden"}), 403
        return jsonify(_build_report())

bp = Blueprint("debug_admin", __name__, url_prefix="/admin")


@bp.get("/debug")
def debug_page():
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    remote_addr = request.remote_addr or ''
    html = f"""
    <html><head><title>Admin Debug</title>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <style>
    body {{ background: #0b1220; color: #e0e6f0; font-family: 'Segoe UI', Arial, sans-serif; margin: 0; }}
    .container {{ max-width: 980px; margin: 48px auto; background: #181f2f; border-radius: 12px; box-shadow: 0 2px 16px #0008; padding: 40px 32px 24px 32px; text-align: center; }}
    h1 {{ font-size: 2.8em; margin-bottom: 0.2em; letter-spacing: 1px; }}
    .badge {{ display: inline-block; background: #1e293b; color: #aaffaa; font-size: 1.2em; border-radius: 8px; padding: 8px 18px; margin: 18px 0 32px 0; font-weight: 600; letter-spacing: 1px; }}
    .btn {{ display: inline-block; margin: 0 12px; padding: 12px 28px; font-size: 1.1em; border-radius: 6px; border: none; background: #2e3a5c; color: #fff; cursor: pointer; font-weight: 500; transition: background 0.2s; }}
    .btn:hover {{ background: #3b4a6a; }}
    .footer {{ margin-top: 48px; color: #7a869a; font-size: 0.98em; }}
    </style></head>
    <body><div class='container'>
    <h1>Admin Debug</h1>
    <div class='badge'>debug_admin loaded ✅</div><br>
    <button class='btn' onclick="window.open('/admin/debug/report.json','_blank')">Open JSON report</button>
    <button class='btn' onclick="navigator.clipboard.writeText(window.location.href)">Copy URL</button>
    <div class='footer'>
      <div>UTC: {now}</div>
      <div>IP: {remote_addr}</div>
    </div>
    </div></body></html>
    """
    return Response(html, mimetype="text/html")


@bp.get("/debug/report.json")
def debug_report():
    is_admin = bool(session.get("is_admin")) or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    cfg = current_app.config
    now = datetime.utcnow().isoformat() + 'Z'
    commit = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or os.getenv("RENDER_GIT_COMMIT") or "dev"
    env = {
        "uploads_root": cfg.get("UPLOADS_ROOT"),
        "media_root": cfg.get("MEDIA_ROOT"),
        "has_cloudinary": bool(os.getenv("CLOUDINARY_URL")),
        "has_db": bool(os.getenv("DATABASE_URL")),
    }
    bp_status = cfg.get("DEBUG_BP_STATUS", {})
    import_errors = cfg.get("DEBUG_IMPORT_ERRORS", {})
    errors = list(cfg.get("DEBUG_ERRORS", []))
    rules = [r.rule for r in current_app.url_map.iter_rules()]
    filter_keys = ["/admin", "/market", "/api/market", "/api/lang"]
    filtered_routes = [r for r in rules if any(k in r for k in filter_keys)]
    return jsonify({
        "ok": True,
        "ts_utc": now,
        "commit": commit,
        "env": env,
        "bp_status": bp_status,
        "import_errors": import_errors,
        "errors": errors,
        "routes": {"count": len(filtered_routes), "list": filtered_routes},
    })

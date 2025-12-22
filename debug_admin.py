from __future__ import annotations

import os
from flask import Blueprint, Response, jsonify, session, request
from datetime import datetime

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
    return jsonify({"ok": True, "module": __file__})

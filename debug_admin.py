from __future__ import annotations

import os
from flask import Blueprint, Response, jsonify, session

bp = Blueprint("debug_admin", __name__, url_prefix="/admin")


@bp.get("/debug")
def debug_page():
    return Response(
        "<h1>Admin Debug</h1><p>debug_admin loaded ✅</p>",
        mimetype="text/html",
    )


@bp.get("/debug/report.json")
def debug_report():
    is_admin = bool(session.get("is_admin")) or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True, "module": __file__})

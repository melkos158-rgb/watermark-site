from __future__ import annotations

import os
from flask import Blueprint, Response, jsonify, session

bp = Blueprint("debug_admin", __name__, url_prefix="/admin")

@bp.get("/debug")
def debug_page():
    return Response("<h1>Admin Debug</h1><p>debug_admin loaded ✅</p>", mimetype="text/html")

@bp.get("/debug/report.json")
def debug_report():
    is_admin = bool(session.get("is_admin")) or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True, "module": __file__})
from __future__ import annotations
import os
from flask import Blueprint, Response, jsonify, session

bp = Blueprint("debug_admin", __name__, url_prefix="/admin")

@bp.get("/debug")
def debug_page():
    return Response(
        "<h1>Admin Debug</h1><p>debug_admin loaded ✅</p>",
        mimetype="text/html"
    )

@bp.get("/debug/report.json")
def debug_report():
    is_admin = bool(session.get("is_admin")) or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True})
from __future__ import annotations

import os
from flask import Blueprint, Response, jsonify, session

bp = Blueprint("debug_admin", __name__, url_prefix="/admin")


@bp.get("/debug")
def debug_page():
    return Response("<h1>Admin Debug</h1><p>debug_admin loaded ✅</p>", mimetype="text/html")


@bp.get("/debug/report.json")
def debug_report():
    is_admin = bool(session.get("is_admin")) or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True, "module": __file__})
from __future__ import annotations

import os
from flask import Blueprint, Response, jsonify, session

bp = Blueprint("debug_admin", __name__, url_prefix="/admin")

@bp.get("/debug")
def debug_page():
    return Response("<h1>Admin Debug</h1><p>debug_admin loaded ✅</p>", mimetype="text/html")

@bp.get("/debug/report.json")
def debug_report():
    is_admin = bool(session.get("is_admin")) or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True, "module": __file__})
bp = Blueprint("debug_admin", __name__, url_prefix="/admin")
from __future__ import annotations

from flask import Blueprint, Response, jsonify

bp = Blueprint("debug_admin", __name__, url_prefix="/admin")

@bp.get("/debug")
def debug_page():
    return Response("<h1>Admin Debug</h1><p>debug_admin loaded ✅</p>", mimetype="text/html")

@bp.get("/debug/report.json")
def debug_report():
    return jsonify({"ok": True, "module": __file__})
@bp.route("/admin/debug/report.json")
def admin_debug_report():
    uid = session.get("user_id")
    is_admin = session.get("is_admin") or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"error": "Forbidden"}), 403

    from flask import Blueprint, Response
bp = Blueprint("debug_admin", __name__, url_prefix="/admin")  # This line is retained for context

    @bp.get("/debug")
    def debug_page():  # Renamed function to match the new intent
        return Response("<h1>Debug Admin OK</h1>", mimetype="text/html")
        return "Forbidden", 403
    env = {
        "UPLOADS_ROOT": current_app.config.get("UPLOADS_ROOT"),
        "CLOUDINARY_URL": os.environ.get("CLOUDINARY_URL"),
    }
    health = {}
    import requests
    for url in ["/market", "/api/items"]:
        try:
            r = requests.get(request.host_url.rstrip("/") + url)
            health[url] = r.status_code
        except Exception as e:
            health[url] = str(e)
    return render_template("admin_debug.html", errors=_ERRORS[-20:], env=env, health=health)

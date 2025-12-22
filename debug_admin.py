@bp.route("/admin/debug/report.json")
def admin_debug_report():
    uid = session.get("user_id")
    is_admin = session.get("is_admin") or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"error": "Forbidden"}), 403
    env = {
        "UPLOADS_ROOT": current_app.config.get("UPLOADS_ROOT"),
        "CLOUDINARY_URL": bool(os.environ.get("CLOUDINARY_URL")),
    }
    health = {}
    import requests
    for url in ["/market", "/api/items"]:
        try:
            r = requests.get(request.host_url.rstrip("/") + url)
            health[url] = r.status_code
        except Exception as e:
            health[url] = str(e)
    report = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "env": env,
        "health": health,
        "backend_errors": _ERRORS[-20:],
        "client_errors": request.args.get("client_errors"),
        "request_ids": [e.get("request_id") for e in _ERRORS[-20:] if e.get("request_id")],
    }
    return jsonify(report)
from flask import Blueprint, request, jsonify, session, render_template, current_app, g
import uuid, os, datetime

bp = Blueprint("debug_admin", __name__)

# Store latest errors in memory (for demo, not production)
_ERRORS = []


# Attach request_id before each request
@bp.before_app_request
def attach_request_id():
    rid = str(uuid.uuid4())
    g.request_id = rid
    request.request_id = rid

# Attach X-Request-Id header after each request
@bp.after_app_request
def add_request_id_header(resp):
    rid = getattr(g, "request_id", None)
    if rid:
        resp.headers["X-Request-Id"] = rid
    return resp

@bp.app_errorhandler(Exception)
def handle_exception(e):
    import traceback
    rid = getattr(g, "request_id", None) or str(uuid.uuid4())
    tb = traceback.format_exc()
    err = {
        "error": True,
        "message": str(e),
        "trace": tb,
        "request_id": rid,
        "url": request.path,
        "ts": datetime.datetime.utcnow().isoformat()
    }
    _ERRORS.append(err)
    if request.path.startswith("/api/"):
        return jsonify(error=True, message=str(e), request_id=rid), 500
    # Return plain text for non-API errors
    return (
        f"[DEBUG ERROR] Request ID: {rid}\nURL: {request.path}\nMessage: {str(e)}\nTrace:\n{tb}",
        500,
        {"Content-Type": "text/plain"}
    )

@bp.route("/admin/debug")
def admin_debug():
    # Only admin or DEV
    uid = session.get("user_id")
    is_admin = session.get("is_admin") or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
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

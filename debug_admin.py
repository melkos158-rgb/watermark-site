@bp.route("/admin/debug/report.json")
def admin_debug_report():
    uid = session.get("user_id")
    is_admin = session.get("is_admin") or os.environ.get("FLASK_ENV") == "development"
    if not is_admin:
        return jsonify({"error": "Forbidden"}), 403

    from flask import Blueprint, Response
    bp = Blueprint("debug_admin", __name__, url_prefix="/admin")

    @bp.get("/debug")
    def admin_debug():
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

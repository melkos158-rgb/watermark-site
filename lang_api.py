from flask import Blueprint, g, jsonify, request, session

from db import db

# 🔧 Blueprint без url_prefix — префікс даємо в app.register_blueprint(...)
bp = Blueprint("lang_api", __name__)


@bp.post("/set")
def set_lang():
    data = request.get_json(silent=True) or {}
    lang = (data.get("lang") or "").lower()[:8]
    if not lang:
        return jsonify({"ok": False, "error": "no lang"}), 400

    session["lang"] = lang

    if getattr(g, "user", None):
        g.user.lang = lang
        try:
            db.session.add(g.user)
            db.session.commit()
        except Exception:
            db.session.rollback()

    return jsonify({"ok": True, "lang": lang})


@bp.get("/me")
def me_lang():
    lang = None
    if getattr(g, "user", None) and getattr(g.user, "lang", None):
        lang = g.user.lang
    if not lang:
        lang = session.get("lang")
    return jsonify({"lang": (lang or "uk").lower()})

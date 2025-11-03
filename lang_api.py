from flask import Blueprint, request, jsonify, session, g
from db import db

lang_api = Blueprint("lang_api", __name__, url_prefix="/api/lang")

@lang_api.post("/set")
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

@lang_api.get("/me")
def me_lang():
    lang = None
    if getattr(g, "user", None) and getattr(g.user, "lang", None):
        lang = g.user.lang
    if not lang:
        lang = session.get("lang")
    return jsonify({"lang": (lang or "uk").lower()})

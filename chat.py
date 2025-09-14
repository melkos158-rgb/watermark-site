# chat.py
from flask import Blueprint, request, jsonify, session, g
from db import get_db

bp = Blueprint("chat", __name__, url_prefix="/chat")

def _who():
    # витягуємо поточного користувача (як у тебе в auth/profile)
    uid = session.get("user_id")
    name = session.get("name") or "Гість"
    email = session.get("email")
    return uid, name, email

@bp.route("/post", methods=["POST"])
def post_message():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400
    uid, name, email = _who()
    try:
        db = get_db()
        db.execute(
            "INSERT INTO messages (user_id, user_name, user_email, text) VALUES (?, ?, ?, ?)",
            (uid, name, email, text[:2000])
        )
        db.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": "db"}), 500

@bp.route("/fetch")
def fetch():
    """
    GET /chat/fetch?since_id=123
    повертає максимум 50 останніх (або з since_id)
    """
    since_id = request.args.get("since_id", type=int)
    db = get_db()
    if since_id:
        rows = db.execute(
            "SELECT id, user_name, text, strftime('%H:%M', created_at) as time "
            "FROM messages WHERE id > ? ORDER BY id ASC LIMIT 50",
            (since_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, user_name, text, strftime('%H:%M', created_at) as time "
            "FROM messages ORDER BY id DESC LIMIT 50"
        ).fetchall()
        rows = list(rows)[::-1]  # від старіших до новіших
    msgs = [dict(r) if hasattr(r, "keys") else dict(r) for r in rows]
    return jsonify({"ok": True, "messages": msgs})

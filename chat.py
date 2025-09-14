# chat.py
from flask import Blueprint, request, jsonify, session
from db import get_db

bp = Blueprint("chat", __name__, url_prefix="/chat")

def _user():
    return (
        session.get("user_id"),
        session.get("name") or "Гість",
        session.get("email"),
    )

@bp.route("/post", methods=["POST"])
def post_message():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400
    uid, name, email = _user()
    try:
        db = get_db()
        db.execute(
            "INSERT INTO messages (user_id, user_name, user_email, text) VALUES (?, ?, ?, ?)",
            (uid, name, email, text[:2000]),
        )
        db.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": "db"}), 500

@bp.route("/fetch")
def fetch():
    """
    GET /chat/fetch?since_id=123
    Повертає останні 50 (або новіші за since_id). Формат часу робимо на Python — працює і з SQLite, і з Postgres.
    """
    since_id = request.args.get("since_id", type=int) or 0
    db = get_db()
    if since_id > 0:
        rows = db.execute(
            "SELECT id, user_name, text, created_at FROM messages WHERE id > ? ORDER BY id ASC LIMIT 50",
            (since_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, user_name, text, created_at FROM messages ORDER BY id DESC LIMIT 50"
        ).fetchall()
        rows = list(rows)[::-1]

    import datetime
    out = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else dict(r)
        created = d.get("created_at")
        # created може бути str (SQLite) або datetime (PG). Робимо HH:MM:
        t = ""
        try:
            if isinstance(created, datetime.datetime):
                t = created.strftime("%H:%M")
            else:
                # пробуємо ISO-рядок
                s = str(created)
                # швидкий зріз HH:MM
                if len(s) >= 16 and s[11:16].replace(":", "").isdigit():
                    t = s[11:16]
                else:
                    try:
                        t = datetime.datetime.fromisoformat(s).strftime("%H:%M")
                    except Exception:
                        t = ""
        except Exception:
            t = ""
        out.append({"id": d.get("id"), "user_name": d.get("user_name"), "text": d.get("text"), "time": t})

    return jsonify({"ok": True, "messages": out})


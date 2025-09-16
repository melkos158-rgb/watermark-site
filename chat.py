# chat.py
from flask import Blueprint, request, jsonify, session
from sqlalchemy import select
from datetime import datetime
from db import db, User, Message

bp = Blueprint("chat", __name__, url_prefix="/chat")

# ---------- helpers (пристосування під різні схеми Message) ----------

def _msg_get_text(m) -> str:
    # підтримує як Message.text, так і Message.body
    if hasattr(m, "text"):
        return m.text or ""
    if hasattr(m, "body"):
        return m.body or ""
    return ""

def _msg_set_text(m, text: str):
    if hasattr(m, "text"):
        setattr(m, "text", text)
    elif hasattr(m, "body"):
        setattr(m, "body", text)
    else:
        raise RuntimeError("Message model has neither 'text' nor 'body'")

def _msg_get_user_id(m):
    # спершу user_id (глобальний чат), інакше sender_id (якщо у тебе була DM-схема)
    if hasattr(m, "user_id"):
        return getattr(m, "user_id")
    if hasattr(m, "sender_id"):
        return getattr(m, "sender_id")
    return None

def _msg_set_user_id(m, uid):
    if hasattr(m, "user_id"):
        setattr(m, "user_id", uid)
    elif hasattr(m, "sender_id"):
        setattr(m, "sender_id", uid)
    # якщо ні, просто ігноруємо

def _msg_get_created_at(m):
    ts = getattr(m, "created_at", None)
    return ts

def _fmt_time(ts) -> str:
    try:
        if isinstance(ts, datetime):
            return ts.strftime("%H:%M")
    except Exception:
        pass
    return ""

def _user_name(uid) -> str:
    if not uid:
        return "Гість"
    u = db.session.get(User, uid)
    if not u:
        return "Гість"
    return (u.name or u.email) or "Гість"

def _dto(m):
    return {
        "id": m.id,
        "text": _msg_get_text(m),
        "user_name": _user_name(_msg_get_user_id(m)),
        "time": _fmt_time(_msg_get_created_at(m)),
    }

# ---------- API під віджет (ГЛОБАЛЬНИЙ ЧАТ) ----------

@bp.get("/fetch")
def fetch():
    """
    Повертає початкову історію або довантажує нові повідомлення після since_id.
    Формат відповіді: { ok: true, messages: [{id, text, user_name, time}, ...] }
    """
    since_id = request.args.get("since_id", type=int)
    stmt = select(Message).order_by(Message.id.asc())
    if since_id:
        stmt = stmt.where(Message.id > since_id)
    rows = db.session.execute(stmt).scalars().all()
    return jsonify({"ok": True, "messages": [_dto(m) for m in rows]})

@bp.post("/post")
def post():
    """
    Приймає JSON: { "text": "..." }
    Зберігає повідомлення. Автор — користувач з сесії або "Гість".
    Формат відповіді: { ok: true, message: {id, text, user_name, time} }
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400

    uid = session.get("user_id")  # може бути None для гостя

    # створення універсально під різну схему Message
    m = Message()
    _msg_set_text(m, text)
    _msg_set_user_id(m, uid)

    db.session.add(m)
    db.session.commit()

    return jsonify({"ok": True, "message": _dto(m)})


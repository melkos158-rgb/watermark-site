# chat.py
from flask import Blueprint, request, jsonify, session
from sqlalchemy import select
from datetime import datetime
from db import db, User, Message

bp = Blueprint("chat", __name__, url_prefix="/chat")

# ---------- helpers: уніфікуємо різні назви полів ----------

def _msg_get_text(m) -> str:
    if hasattr(m, "text"):
        return m.text or ""
    if hasattr(m, "body"):
        return m.body or ""
    return ""

def _msg_set_text(m, text: str):
    if hasattr(m, "text"):
        m.text = text
    elif hasattr(m, "body"):
        m.body = text
    else:
        raise RuntimeError("Message model has neither 'text' nor 'body'")

def _msg_get_user_id(m):
    if hasattr(m, "user_id"):
        return m.user_id
    if hasattr(m, "sender_id"):
        return m.sender_id
    return None

def _msg_set_user_id(m, uid):
    if hasattr(m, "user_id"):
        m.user_id = uid
    elif hasattr(m, "sender_id"):
        m.sender_id = uid

def _ensure_global_chat_defaults(m, uid):
    """
    Якщо в моделі є recipient_id (історія з приватними ДМ) — для глобального чату
    отримувача нема, тому ставимо None.
    Якщо у тебе в БД recipient_id = NOT NULL, можеш ТИМЧАСОВО підставити відправника:
        m.recipient_id = uid
    але правильніше: зробити recipient_id NULLABLE.
    """
    if hasattr(m, "recipient_id"):
        try:
            m.recipient_id = None
            # >>> Якщо у твоїй схемі recipient_id обовʼязковий — розкоментуй наступний рядок:
            # if m.recipient_id is None and uid is not None: m.recipient_id = uid
        except Exception:
            pass

def _fmt_time(ts) -> str:
    if isinstance(ts, datetime):
        return ts.strftime("%H:%M")
    return ""

def _user_name(uid) -> str:
    if not uid:
        return "Гість"
    u = db.session.get(User, uid)
    return (u.name or u.email) if u else "Гість"

def _dto(m):
    return {
        "id": m.id,
        "text": _msg_get_text(m),
        "user_name": _user_name(_msg_get_user_id(m)),
        "time": _fmt_time(getattr(m, "created_at", None)),
    }

# ---------- API для віджета ----------

@bp.get("/fetch")
def fetch():
    """
    Повертає історію (або лише нові після ?since_id).
    Відповідь: { ok: true, messages: [{id, text, user_name, time}, ...] }
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
    Приймає JSON: { "text": "..." } і додає повідомлення від користувача з сесії
    (або від гостя, якщо не залогінений). Повертає { ok: true, message: {...} }.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400

    uid = session.get("user_id")  # може бути None для гостя

    m = Message()
    _msg_set_text(m, text)
    _msg_set_user_id(m, uid)
    _ensure_global_chat_defaults(m, uid)

    db.session.add(m)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # Найчастіше тут падає NOT NULL / FK на recipient_id
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "message": _dto(m)})

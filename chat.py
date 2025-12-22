# chat.py
from datetime import datetime

from flask import Blueprint, jsonify, request, session
from sqlalchemy import select

from db import Message, User, db

bp = Blueprint("chat", __name__, url_prefix="/chat")

# ---------- helpers ----------

def _get_text(m) -> str:
    return getattr(m, "text", None) or getattr(m, "body", "") or ""

def _set_text(m, text: str):
    if hasattr(m, "text"):
        m.text = text
    elif hasattr(m, "body"):
        m.body = text
    else:
        raise RuntimeError("Message has neither 'text' nor 'body' column")

def _get_user_id(m):
    if hasattr(m, "user_id"):
        return m.user_id
    if hasattr(m, "sender_id"):
        return m.sender_id
    return None

def _set_user_id(m, uid):
    if hasattr(m, "user_id"):
        m.user_id = uid
    elif hasattr(m, "sender_id"):
        m.sender_id = uid

def _human_name(uid):
    if not uid:
        return "Гість"
    u = db.session.get(User, uid)
    return (u.name or u.email) if u else "Гість"

def _fmt_time(ts):
    return ts.strftime("%H:%M") if isinstance(ts, datetime) else ""

def _dto(m):
    uid = _get_user_id(m)
    return {
        "id": m.id,
        "text": _get_text(m),
        "user_id": uid,                      # ВАЖЛИВО: фронт визначає .me по цьому полю
        "user_name": _human_name(uid),
        "time": _fmt_time(getattr(m, "created_at", None)),
    }

def _apply_global_defaults(m, uid):
    # Якщо є recipient_id і він None — ставимо відправника (за потреби)
    if hasattr(m, "recipient_id") and getattr(m, "recipient_id", None) is None:
        if uid is not None:
            m.recipient_id = uid
    # Якщо created_at без дефолту в БД — поставимо зараз (UTC)
    if hasattr(m, "created_at") and getattr(m, "created_at", None) is None:
        m.created_at = datetime.utcnow()

# ---------- API ----------

@bp.get("/fetch")
def fetch():
    since_id = request.args.get("since_id", type=int)
    stmt = select(Message).order_by(Message.id.asc())
    if since_id:
        stmt = stmt.where(Message.id > since_id)
    rows = db.session.execute(stmt).scalars().all()
    return jsonify({"ok": True, "messages": [_dto(m) for m in rows]})

@bp.post("/post")
def post():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400

    uid = session.get("user_id")  # None для гостя

    m = Message()
    _set_text(m, text)
    _set_user_id(m, uid)
    _apply_global_defaults(m, uid)

    db.session.add(m)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "message": _dto(m)})

# Діагностика: подивитись, що реально лежить у БД
@bp.get("/debug")
def debug():
    rows = db.session.execute(
        select(Message).order_by(Message.id.desc()).limit(5)
    ).scalars().all()
    return jsonify({
        "ok": True,
        "last": [
            {
                "id": m.id,
                "sender_id": getattr(m, "sender_id", None),
                "recipient_id": getattr(m, "recipient_id", None),
                "user_id": getattr(m, "user_id", None),
                "text": _get_text(m),
                "created_at": getattr(m, "created_at", None).isoformat() if getattr(m, "created_at", None) else None
            } for m in rows
        ]
    })

# ---- ДОДАНО: віддати свій user_id із сесії (корисно фронту) ----
@bp.get("/me")
def me():
    uid = session.get("user_id")
    u = db.session.get(User, uid) if uid else None
    return jsonify({
        "ok": True,
        "user_id": uid,
        "name": (u.name or u.email) if u else "Гість",
        "avatar": getattr(u, "avatar", None) if u else None
    })

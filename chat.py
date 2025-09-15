# chat.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, abort
from sqlalchemy import or_, and_
from datetime import datetime
from db import db, User, Message  # ← ORM моделі, НІЯКОГО get_db

bp = Blueprint("chat", __name__, url_prefix="/chat")


# -----------------------------
# helpers
# -----------------------------
def _current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None

def _require_user():
    u = _current_user()
    if not u:
        flash("Спочатку увійди.", "error")
        return None
    return u


# -----------------------------
# UI: простий чат-екран
#   GET /chat           → список юзерів + останні повідомлення з вибраним
#   GET /chat?uid=123   → відкрити тред з юзером 123
# -----------------------------
@bp.get("/")
def index():
    u = _require_user()
    if not u:
        return redirect(url_for("auth.login"))

    # список співрозмовників (поки всі інші користувачі)
    users = User.query.filter(User.id != u.id).order_by(User.id.asc()).limit(200).all()

    # якщо передали конкретного отримувача — підтягнемо тред
    partner_id = request.args.get("uid", type=int)
    thread = []
    partner = None
    if partner_id:
        partner = User.query.get(partner_id)
        if not partner:
            flash("Користувача не знайдено.", "error")
            return redirect(url_for("chat.index"))
        thread = _load_thread(u.id, partner_id, limit=100)

    # рендеримо шаблон (якщо у тебе вже є власний — заміни 'chat.html' на свій)
    try:
        return render_template("chat.html", users=users, me=u, partner=partner, thread=thread)
    except Exception:
        # fallback: якщо шаблону нема, повернемо мінімальний HTML
        return (
            "<h2>Chat</h2>"
            f"<p>Your ID: {u.id} ({u.email})</p>"
            + ("<p>Select a user with ?uid=ID</p>" if not partner else f"<p>Chat with {partner.email}</p>")
        )


# -----------------------------
# API: отримати тред (JSON)
#   GET /chat/thread?uid=123
# -----------------------------
@bp.get("/thread")
def thread_json():
    u = _require_user()
    if not u:
        return abort(401)
    partner_id = request.args.get("uid", type=int)
    if not partner_id:
        return jsonify(ok=False, error="uid is required"), 400
    if not User.query.get(partner_id):
        return jsonify(ok=False, error="user not found"), 404

    data = _load_thread(u.id, partner_id, limit=200)
    return jsonify(ok=True, messages=[
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "recipient_id": m.recipient_id,
            "body": m.body,
            "created_at": m.created_at.isoformat()
        } for m in data
    ])


def _load_thread(a_id: int, b_id: int, limit: int = 100):
    """Всі повідомлення між двома користувачами, за зростанням часу."""
    q = Message.query.filter(
        or_(
            and_(Message.sender_id == a_id, Message.recipient_id == b_id),
            and_(Message.sender_id == b_id, Message.recipient_id == a_id),
        )
    ).order_by(Message.id.asc())
    if limit:
        q = q.limit(limit)
    return q.all()


# -----------------------------
# Надіслати повідомлення (HTML-форма)
#   POST /chat/send
# body: to_id, body
# -----------------------------
@bp.post("/send")
def send():
    u = _require_user()
    if not u:
        return redirect(url_for("auth.login"))

    to_id = request.form.get("to_id", type=int)
    body = (request.form.get("body") or "").strip()

    if not to_id or not body:
        flash("Заповни отримувача і текст.", "error")
        return redirect(url_for("chat.index"))

    if to_id == u.id:
        flash("Не можна писати самому собі.", "error")
        return redirect(url_for("chat.index", uid=to_id))

    if not User.query.get(to_id):
        flash("Отримувача не знайдено.", "error")
        return redirect(url_for("chat.index"))

    db.session.add(Message(sender_id=u.id, recipient_id=to_id, body=body))
    db.session.commit()
    flash("Надіслано.", "success")
    return redirect(url_for("chat.index", uid=to_id))


# -----------------------------
# API: Надіслати повідомлення (JSON)
#   POST /chat/send.json
# json: { "to_id": 123, "body": "hi" }
# -----------------------------
@bp.post("/send.json")
def send_json():
    u = _require_user()
    if not u:
        return jsonify(ok=False, error="unauthorized"), 401

    payload = request.get_json(silent=True) or {}
    to_id = payload.get("to_id")
    body = (payload.get("body") or "").strip()

    if not isinstance(to_id, int) or not body:
        return jsonify(ok=False, error="to_id (int) and body are required"), 400

    if to_id == u.id:
        return jsonify(ok=False, error="cannot message yourself"), 400

    if not User.query.get(to_id):
        return jsonify(ok=False, error="recipient not found"), 404

    m = Message(sender_id=u.id, recipient_id=to_id, body=body)
    db.session.add(m)
    db.session.commit()

    return jsonify(ok=True, id=m.id, created_at=m.created_at.isoformat())



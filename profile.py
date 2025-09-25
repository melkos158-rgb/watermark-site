# profile.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import db, User, Transaction, Message

bp = Blueprint("profile", __name__, url_prefix="")

def _current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None

def _require_user():
    u = _current_user()
    if not u:
        flash("Спочатку увійди.", "error")
        return redirect(url_for("auth.login"))
    return u

@bp.get("/profile")
def profile():
    u = _require_user()
    if not isinstance(u, User):  # redirect
        return u
    tx = Transaction.query.filter_by(user_id=u.id).order_by(Transaction.id.desc()).limit(20).all()
    return render_template("profile.html", user=u, tx=tx)

@bp.post("/profile/update")
def profile_update():
    u = _require_user()
    if not isinstance(u, User): return u
    u.name   = request.form.get("name") or u.name
    u.bio    = request.form.get("bio") or u.bio
    u.avatar = request.form.get("avatar") or u.avatar
    db.session.commit()
    flash("Профіль збережено.", "success")
    return redirect(url_for("profile.profile"))

@bp.get("/donate")
def donate():
    return render_template("donate.html")

@bp.post("/donate")
def donate_post():
    u = _require_user()
    if not isinstance(u, User): return u
    amount = int(request.form.get("amount") or 0)
    if amount <= 0:
        flash("Сума має бути > 0", "error")
        return redirect(url_for("profile.donate"))
    u.pxp += amount
    db.session.add(Transaction(user_id=u.id, amount=amount, kind="donate", note="manual"))
    db.session.commit()
    flash(f"+{amount} PXP зараховано.", "success")
    return redirect(url_for("profile.profile"))

@bp.post("/spend")
def spend():
    u = _require_user()
    if not isinstance(u, User): return u
    amount = int(request.form.get("amount") or 0)
    if amount <= 0 or amount > u.pxp:
        flash("Невірна сума.", "error")
        return redirect(url_for("profile.profile"))
    note = request.form.get("note") or ""
    u.pxp -= amount
    db.session.add(Transaction(user_id=u.id, amount=-amount, kind="spend", note=note))
    db.session.commit()
    flash(f"-{amount} PXP витрачено.", "success")
    return redirect(url_for("profile.profile"))

@bp.get("/top100")
def top100():
    rows = User.query.order_by(User.pxp.desc(), User.id.asc()).limit(100).all()
    return render_template("top100.html", rows=rows)

# --- повідомлення ---
@bp.get("/messages")
def messages():
    u = _require_user()
    if not isinstance(u, User): return u
    inbox = Message.query.filter_by(recipient_id=u.id).order_by(Message.id.desc()).all()
    users = User.query.order_by(User.id.asc()).limit(100).all()
    return render_template("messages.html", inbox=inbox, users=users)

@bp.post("/messages/send")
def send_message():
    u = _require_user()
    if not isinstance(u, User): return u
    to_id = int(request.form.get("to_id") or 0)
    body  = (request.form.get("body") or "").strip()
    if not to_id or not body:
        flash("Заповни поля.", "error"); return redirect(url_for("profile.messages"))
    if not User.query.get(to_id):
        flash("Отримувача не знайдено.", "error"); return redirect(url_for("profile.messages"))
    db.session.add(Message(sender_id=u.id, recipient_id=to_id, body=body))
    db.session.commit()
    flash("Надіслано.", "success")
    return redirect(url_for("profile.messages"))

def donate():
    return render_template("donate.html")
from flask import jsonify

@bp.get("/api/pxp/top100")
def api_top100():
    period = request.args.get("period", "all")
    q = User.query

    # приклад фільтрації, зараз тільки all
    if period == "month":
        q = q.order_by(User.pxp_month.desc(), User.id.asc())
    else:
        q = q.order_by(User.pxp.desc(), User.id.asc())

    rows = q.limit(100).all()

    uid = session.get("user_id")
    me_rank, me_pxp = None, None
    if uid:
        # знаходимо поточний ранг користувача
        if period == "month":
            ordered = User.query.order_by(User.pxp_month.desc(), User.id.asc()).all()
            me_pxp = next((u.pxp_month for u in ordered if u.id == uid), 0)
        else:
            ordered = User.query.order_by(User.pxp.desc(), User.id.asc()).all()
            me_pxp = next((u.pxp for u in ordered if u.id == uid), 0)
        for i, u in enumerate(ordered, start=1):
            if u.id == uid:
                me_rank = i
                break

    data = {
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "pxp": u.pxp,
                "pxp_month": getattr(u, "pxp_month", None),
                "created_at": u.created_at.isoformat() if hasattr(u, "created_at") else None,
            }
            for u in rows
        ],
        "me_rank": me_rank,
        "me_pxp": me_pxp,
    }
    return jsonify(data)

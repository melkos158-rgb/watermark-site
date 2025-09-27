# profile.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from db import db, User, Transaction, Message
from datetime import datetime, timedelta
from sqlalchemy import func, desc

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

# --- helpers (додано) --------------------------------------------------------
def _to_iso(value):
    """Повертає ISO-рядок для datetime або як є, якщо це вже рядок; інакше None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return str(value)
    except Exception:
        return None

def _to_int(value, default=0):
    """Безпечне перетворення в int (бо pxp/pxp_month можуть бути рядками)."""
    try:
        return int(value)
    except Exception:
        return default

def _month_bounds(now=None):
    """Початок та початок наступного місяця (UTC-наївно)."""
    now = now or datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return start, next_start
# -----------------------------------------------------------------------------


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
    u.pxp = _to_int(getattr(u, "pxp", 0)) + amount
    db.session.add(Transaction(user_id=u.id, amount=amount, kind="donate", note="manual"))
    db.session.commit()
    flash(f"+{amount} PXP зараховано.", "success")
    return redirect(url_for("profile.profile"))

@bp.post("/spend")
def spend():
    u = _require_user()
    if not isinstance(u, User): return u
    amount = int(request.form.get("amount") or 0)
    cur = _to_int(getattr(u, "pxp", 0))
    if amount <= 0 or amount > cur:
        flash("Невірна сума.", "error")
        return redirect(url_for("profile.profile"))
    note = request.form.get("note") or ""
    u.pxp = cur - amount
    db.session.add(Transaction(user_id=u.id, amount=-amount, kind="spend", note=note))
    db.session.commit()
    flash(f"-{amount} PXP витрачено.", "success")
    return redirect(url_for("profile.profile"))

@bp.get("/top100")
def top100():
    """Топ за ВСІ ЧАСИ за сумою донатів (kind='donate', amount>0)."""
    # агрегат по донатах
    agg = (
        db.session.query(
            Transaction.user_id.label("uid"),
            func.coalesce(func.sum(Transaction.amount), 0).label("donated"),
        )
        .filter(Transaction.kind == "donate", Transaction.amount > 0)
        .group_by(Transaction.user_id)
        .subquery()
    )

    # приєднуємо до користувачів
    rows = (
        db.session.query(
            User,
            func.coalesce(agg.c.donated, 0).label("donated")
        )
        .outerjoin(agg, agg.c.uid == User.id)
        .order_by(desc("donated"), User.id.asc())
        .limit(100)
        .all()
    )

    # передамо у шаблон як список словників (user, donated)
    data = [{"user": u, "donated": d} for (u, d) in rows]
    return render_template("top100.html", rows=data)

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

@bp.get("/api/pxp/top100")
def api_top100():
    """API-топ: ранжуємо тільки за донатами. ?period=all|month"""
    period = request.args.get("period", "all")

    # базовий фільтр по донатам
    filters = [Transaction.kind == "donate", Transaction.amount > 0]

    # період місяць — беремо лише транзакції поточного місяця
    if period == "month":
        start, next_start = _month_bounds()
        filters.append(Transaction.created_at >= start)
        filters.append(Transaction.created_at < next_start)

    # агрегуємо
    agg_q = (
        db.session.query(
            Transaction.user_id.label("uid"),
            func.coalesce(func.sum(Transaction.amount), 0).label("donated"),
        )
        .filter(*filters)
        .group_by(Transaction.user_id)
    )
    agg_sq = agg_q.subquery()

    # приєднуємо до користувачів і ранжуємо
    ranked_q = (
        db.session.query(
            User,
            func.coalesce(agg_sq.c.donated, 0).label("donated")
        )
        .outerjoin(agg_sq, agg_sq.c.uid == User.id)
        .order_by(desc("donated"), User.id.asc())
    )

    # топ-100
    top_rows = ranked_q.limit(100).all()

    # повний порядок для обчислення рангу поточного користувача
    all_rows = ranked_q.all()

    uid = session.get("user_id")
    me_rank, me_donated = None, None
    if uid:
        for i, (u, donated) in enumerate(all_rows, start=1):
            if u.id == uid:
                me_rank = i
                me_donated = int(donated or 0)
                break

    data = {
        "items": [
            {
                "id": u.id,
                "name": getattr(u, "name", None),
                "email": getattr(u, "email", None),
                # залишаємо для зворотної сумісності
                "pxp": _to_int(getattr(u, "pxp", 0)),
                "pxp_month": (_to_int(getattr(u, "pxp_month", 0)) if hasattr(u, "pxp_month") else None),
                "created_at": _to_iso(getattr(u, "created_at", None)),
                "avatar": getattr(u, "avatar", None),
                # нове — сума донатів, за якою будується рейтинг
                "donated": int(donated or 0),
            }
            for (u, donated) in top_rows
        ],
        "me_rank": me_rank,
        # лишаю ключ me_pxp, але тепер це сума донатів користувача
        "me_pxp": me_donated if me_donated is not None else 0,
    }
    return jsonify(data)

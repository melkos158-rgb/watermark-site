import datetime
from typing import Any, Dict, Optional

from flask import (Blueprint, current_app, g, jsonify, render_template,
                   request, session)

from models import db

# ===================== МОДЕЛЬ =====================

class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)

    # Прив’язка до юзера (без FK, щоб не ламати існуючу схему)
    user_id = db.Column(db.Integer, index=True, nullable=True)

    # Тип нотифікації: system / order / comment / ai / printability / other
    type = db.Column(db.String(32), nullable=False, default="system")

    # Рівень: info / success / warning / error
    level = db.Column(db.String(16), nullable=False, default="info")

    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=True)

    # Опційний лінк (куди вести при кліку)
    link = db.Column(db.String(512), nullable=True)

    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    read_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "level": self.level,
            "title": self.title,
            "body": self.body,
            "link": self.link,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }


# ===================== BLUPRINT =====================

notifications_bp = Blueprint("notifications", __name__)


# ===================== УТИЛІТИ =====================

def _get_current_user_id() -> Optional[int]:
    """
    Витягуємо id користувача:
    - спроба g.user.id
    - спроба session["user_id"]
    Якщо немає — повертаємо None (анонім).
    """
    try:
        if hasattr(g, "user") and getattr(g.user, "id", None) is not None:
            return int(g.user.id)
    except Exception:
        pass

    try:
        uid = session.get("user_id")
        if uid is not None:
            return int(uid)
    except Exception:
        pass

    return None


def _user_filter(query):
    """
    Обмежуємо нотифікації лише для поточного користувача.
    Якщо користувач не залогінений — повертаємо пустий набір (анонім нічого не бачить).
    """
    uid = _get_current_user_id()
    if uid is None:
        # немає користувача — нічого не показуємо
        return query.filter(db.text("1=0"))
    return query.filter(Notification.user_id == uid)


def create_notification(
    user_id: Optional[int],
    title: str,
    body: Optional[str] = None,
    *,
    type: str = "system",
    level: str = "info",
    link: Optional[str] = None,
    commit: bool = True,
) -> Notification:
    """
    Хелпер, щоб з будь-якого місця (worker, market_listeners тощо)
    створити нотифікацію:

      from notifications_api import create_notification

      create_notification(
          user_id=user.id,
          title="Замовлення #123 оплачене",
          body="Можна починати друк моделі 'Crystal Dragon'",
          type="order",
          level="success",
          link=url_for("orders.view", order_id=order.id),
      )
    """
    n = Notification(
        user_id=user_id,
        title=title or "Notification",
        body=body,
        type=(type or "system")[:32],
        level=(level or "info")[:16],
        link=link,
    )
    db.session.add(n)
    if commit:
        db.session.commit()
        current_app.logger.info(
            "Created notification id=%s user_id=%s type=%s level=%s",
            n.id,
            n.user_id,
            n.type,
            n.level,
        )
    return n


# ===================== API: LIST / READ =====================

@notifications_bp.route("/api/notifications", methods=["GET"])
def api_list_notifications():
    """
    GET /api/notifications?scope=unread|all

    Відповідь:
      {
        "ok": true,
        "items": [ ... ],
        "unread_count": 5
      }
    """
    uid = _get_current_user_id()
    if uid is None:
        # Анонім — порожній список, без помилки
        return jsonify({"ok": True, "items": [], "unread_count": 0})

    scope = request.args.get("scope", "all").strip().lower()
    q = _user_filter(Notification.query).order_by(Notification.created_at.desc())

    if scope == "unread":
        q = q.filter(Notification.read_at.is_(None))

    # Щоб не вивалюватися великим масивом — обмежимо до 200 останніх
    items = [n.to_dict() for n in q.limit(200).all()]

    unread_q = _user_filter(Notification.query).filter(Notification.read_at.is_(None))
    unread_count = unread_q.count()

    return jsonify({"ok": True, "items": items, "unread_count": unread_count})


@notifications_bp.route("/api/notifications/<int:nid>/read", methods=["POST"])
def api_mark_notification_read(nid: int):
    """
    Позначити конкретну нотифікацію як прочитану.
    POST /api/notifications/<id>/read
    """
    uid = _get_current_user_id()
    if uid is None:
        return jsonify({"ok": False, "error": "Необхідна авторизація."}), 401

    q = _user_filter(Notification.query).filter(Notification.id == nid)
    n = q.first()
    if not n:
        return jsonify({"ok": False, "error": "Нотифікацію не знайдено."}), 404

    if n.read_at is None:
        n.read_at = datetime.datetime.utcnow()
        db.session.commit()

    # Перерахуємо кількість непрочитаних
    unread_q = _user_filter(Notification.query).filter(Notification.read_at.is_(None))
    unread_count = unread_q.count()

    return jsonify({"ok": True, "item": n.to_dict(), "unread_count": unread_count})


@notifications_bp.route("/api/notifications/mark_all_read", methods=["POST"])
def api_mark_all_read():
    """
    Позначити всі нотифікації поточного користувача як прочитані.
    """
    uid = _get_current_user_id()
    if uid is None:
        return jsonify({"ok": False, "error": "Необхідна авторизація."}), 401

    q = _user_filter(Notification.query).filter(Notification.read_at.is_(None))
    now = datetime.datetime.utcnow()
    updated = 0
    for n in q.all():
        n.read_at = now
        updated += 1

    if updated:
        db.session.commit()

    current_app.logger.info(
        "Marked %s notifications as read for user_id=%s", updated, uid
    )

    return jsonify({"ok": True, "unread_count": 0})


# ===================== VIEW ДЛЯ notifications.html =====================

@notifications_bp.route("/notifications", methods=["GET"])
def notifications_page():
    """
    Повертає сторінку зі списком нотифікацій.
    Сам список підтягується з /api/notifications через notifications.js.
    """
    return render_template("notifications.html")

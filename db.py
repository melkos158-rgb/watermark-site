# db.py
import os
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Ініціалізація
db = SQLAlchemy()

# -----------------------------
# МОДЕЛІ
# -----------------------------
class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)           # незмінний числовий ID
    email      = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name       = db.Column(db.String(120))
    bio        = db.Column(db.Text)
    # лишаємо старе поле для сумісності
    avatar     = db.Column(db.Text)                                 # URL або data:image
    # додаємо нове поле, яке очікується у SQL ("u.avatar_url") в market.py
    avatar_url = db.Column(db.Text)                                 # окремий URL-стовпець (може дублювати avatar)
    pxp        = db.Column(db.Integer, default=0, nullable=False)   # баланс PXP
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.id} {self.email} PXP={self.pxp}>"


class Transaction(db.Model):
    __tablename__ = "transactions"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    amount     = db.Column(db.Integer, nullable=False)              # +donate / -spend
    kind       = db.Column(db.String(20), nullable=False, default="manual")  # donate|spend|manual
    note       = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("transactions", lazy=True))

    def __repr__(self):
        return f"<Transaction {self.id} u={self.user_id} {self.kind} {self.amount}>"


class Message(db.Model):
    __tablename__ = "messages"

    id           = db.Column(db.Integer, primary_key=True)
    sender_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    body         = db.Column(db.Text, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    sender    = db.relationship("User", foreign_keys=[sender_id], backref=db.backref("sent_messages", lazy=True))
    recipient = db.relationship("User", foreign_keys=[recipient_id], backref=db.backref("inbox_messages", lazy=True))

    def __repr__(self):
        return f"<Message {self.id} {self.sender_id}->{self.recipient_id}>"


# -----------------------------
# НОВА ТАБЛИЦЯ ДЛЯ ВІЗИТІВ / ОНЛАЙН
# -----------------------------
class Visit(db.Model):
    """
    Зберігає легкий лог відвідувань (1 запис/хв/сесія).
    Використовується запитами в admin_metrics для:
      - онлайн за останні 10 хв
      - унікальні за місяць (DISTINCT COALESCE(user_id, session_id))
    """
    __tablename__ = "visits"

    id         = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    path       = db.Column(db.String(255))
    # server_default -> працює і в Postgres, і в SQLite (як CURRENT_TIMESTAMP)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)

    user = db.relationship("User", backref=db.backref("visits", lazy=True))

    __table_args__ = (
        db.Index("ix_visits_created", "created_at"),
        db.Index("ix_visits_user_session", "user_id", "session_id"),
    )

    def __repr__(self):
        return f"<Visit sid={self.session_id} user={self.user_id} at={self.created_at}>"


# -----------------------------
# INIT & CLOSE
# -----------------------------
def init_app_db(app: Flask):
    """
    Підключає БД до Flask:
    - Якщо є env DATABASE_URL (Railway Postgres) — використовує її
      і виправляє схему postgres:// → postgresql://
    - Інакше SQLite локально: sqlite:///database.db
    """
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config.setdefault("SQLALCHEMY_DATABASE_URI", db_url or "sqlite:///database.db")
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    db.init_app(app)
    with app.app_context():
        db.create_all()  # створить таблицю visits, якщо її ще немає


def close_db(error=None):
    """Закриває сесію SQLAlchemy після кожного запиту (для gunicorn/teardown)."""
    try:
        db.session.remove()
    except Exception:
        pass

# db.py
from flask_sqlalchemy import SQLAlchemy
from flask import Flask
from datetime import datetime

# Ініціалізація SQLAlchemy
db = SQLAlchemy()


# -----------------------------
# МОДЕЛІ
# -----------------------------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)   # Унікальний ID
    email = db.Column(db.String(255), unique=True, nullable=False)  # Логін/Google email
    name = db.Column(db.String(120))               # Ім’я/нік
    bio = db.Column(db.Text)                       # Про себе
    avatar = db.Column(db.Text)                    # URL або data:image
    pxp = db.Column(db.Integer, default=0)         # Баланс PXP
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Дата реєстрації

    def __repr__(self):
        return f"<User {self.id} {self.email} PXP={self.pxp}>"


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # Скільки PXP зараховано/витрачено
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Зв’язок: кожна транзакція належить користувачу
    user = db.relationship("User", backref=db.backref("transactions", lazy=True))

    def __repr__(self):
        return f"<Transaction {self.id} user={self.user_id} amount={self.amount}>"

# -----------------------------
# INIT & CLOSE
# -----------------------------
def init_app_db(app: Flask):
    """
    Підключає базу до Flask app.
    Використовує Postgres (DATABASE_URL), якщо є,
    інакше SQLite для локального запуску.
    """
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config.get(
        "DATABASE_URL", "sqlite:///database.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    # створюємо таблиці при першому запуску
    with app.app_context():
        db.create_all()


def close_db(error=None):
    """Закриває сесію після кожного запиту"""
    try:
        db.session.remove()
    except Exception:
        pass

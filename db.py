# db.py
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask import Flask

db = SQLAlchemy()

def init_app_db(app: Flask):
    # Railway надає postgres:// — треба замінити на postgresql://
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url or "sqlite:///database.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()

# ---- МОДЕЛІ ----
class User(db.Model):
    id        = db.Column(db.Integer, primary_key=True)                 # незмінний числовий id
    email     = db.Column(db.String(255), unique=True, index=True, nullable=False)
    name      = db.Column(db.String(120))
    avatar    = db.Column(db.Text)     # dataURL або url
    bio       = db.Column(db.Text)
    pxp       = db.Column(db.Integer, default=0, nullable=False)
    created_at= db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    amount    = db.Column(db.Integer, nullable=False)   # + для donate, - для spend
    kind      = db.Column(db.String(20), nullable=False) # donate|spend|manual
    note      = db.Column(db.String(255))
    created_at= db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    recipient_id= db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    body        = db.Column(db.Text, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

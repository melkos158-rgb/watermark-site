# models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class MarketItem(db.Model):
    __tablename__ = "market_items"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    price = db.Column(db.Integer, default=0)
    tags = db.Column(db.Text, default="")
    desc = db.Column(db.Text, default="")
    user_id = db.Column(db.Integer)

    # Головне фото
    cover_url = db.Column(db.Text)
    # Список фото (JSON рядок)
    gallery_urls = db.Column(db.Text)
    # Основний STL
    stl_main_url = db.Column(db.Text)
    # Додаткові STL (JSON рядок)
    stl_extra_urls = db.Column(db.Text)

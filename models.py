# models.py
from __future__ import annotations
from datetime import datetime
import json

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class MarketItem(db.Model):
    __tablename__ = "market_items"

    id = db.Column(db.Integer, primary_key=True)

    # базові
    title = db.Column(db.String(200))
    price = db.Column(db.Integer, default=0)
    tags = db.Column(db.Text, default="")
    desc = db.Column(db.Text, default="")
    user_id = db.Column(db.Integer)

    # медіа
    # Головне фото
    cover_url = db.Column(db.Text)
    # Список фото (JSON-рядок)
    gallery_urls = db.Column(db.Text, default="[]")

    # Основний STL
    stl_main_url = db.Column(db.Text)
    # Додаткові STL (JSON-рядок)
    stl_extra_urls = db.Column(db.Text, default="[]")

    # >>> НОВЕ: головний ZIP-архів для завантаження (1 файл)
    zip_url = db.Column(db.Text)

    # корисні таймстампи
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # ---- нижче лиш утиліти, що НЕ ламають жодних існуючих викликів ----
    def _loads(self, value: str | None) -> list[str]:
        try:
            return json.loads(value) if value else []
        except Exception:
            return []

    @property
    def gallery(self) -> list[str]:
        """Список фото як Python-список."""
        return self._loads(self.gallery_urls)

    @property
    def stl_extra(self) -> list[str]:
        """Список додаткових STL як Python-список."""
        return self._loads(self.stl_extra_urls)

    @property
    def preferred_download_url(self) -> str | None:
        """
        Головний файл для скачування:
        1) zip_url, якщо є
        2) stl_main_url, якщо є
        3) перший з stl_extra
        4) None
        """
        if self.zip_url:
            return self.zip_url
        if self.stl_main_url:
            return self.stl_main_url
        extras = self.stl_extra
        return extras[0] if extras else None

    def to_dict(self) -> dict:
        """Зручно віддавати в шаблон/JSON. Не змінює існуючих полів."""
        return {
            "id": self.id,
            "title": self.title,
            "price": self.price,
            "tags": self.tags,
            "desc": self.desc,
            "user_id": self.user_id,
            "cover_url": self.cover_url,
            "gallery_urls": self.gallery,      # вже як список
            "stl_main_url": self.stl_main_url,
            "stl_extra_urls": self.stl_extra,  # вже як список
            "zip_url": self.zip_url,
            "preferred_download_url": self.preferred_download_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

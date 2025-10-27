# models.py
from __future__ import annotations
from datetime import datetime
import json
from typing import Optional, Dict, Any

# >>> використовуємо існуючий інстанс з db.py
from db import db as _db  # реальний Flask-SQLAlchemy


class _DBProxy:
    """
    Проксі над реальним _db:
    - усі атрибути делегуються у _db,
    - init_app(app) — no-op, щоби не дублювати реєстрацію розширення.
    """
    def __getattr__(self, name):
        return getattr(_db, name)

    def init_app(self, app):
        # no-op: справжня ініціалізація вже робиться у init_app_db(app)
        return


# Експортуємо проксі як 'db', щоб у app.py можна було:
#   from models import db as models_db, MarketItem
db = _DBProxy()

__all__ = ["db", "MarketItem"]


class MarketItem(_db.Model):
    # ВАЖЛИВО: market.py працює з таблицею "items"
    __tablename__ = "items"

    # ---------- базові ----------
    id = _db.Column(_db.Integer, primary_key=True)
    title = _db.Column(_db.String(200))
    price = _db.Column(_db.Integer, default=0)
    tags = _db.Column(_db.Text, default="")
    # атрибут 'desc' мапиться на колонку "description"
    desc = _db.Column("description", _db.Text, default="")
    user_id = _db.Column(_db.Integer, index=True)

    # ---------- медіа ----------
    cover_url = _db.Column(_db.Text)
    gallery_urls = _db.Column(_db.Text, default="[]")
    stl_main_url = _db.Column(_db.Text)
    stl_extra_urls = _db.Column(_db.Text, default="[]")
    zip_url = _db.Column(_db.Text)

    # ---------- додаткове ----------
    format = _db.Column(_db.String(16), default="stl")
    rating = _db.Column(_db.Float, default=0)
    downloads = _db.Column(_db.Integer, default=0)

    created_at = _db.Column(_db.DateTime, default=datetime.utcnow, index=True)
    updated_at = _db.Column(_db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ---------- утиліти ----------
    def _loads(self, value: str | None) -> list[str]:
        try:
            return json.loads(value) if value else []
        except Exception:
            return []

    @property
    def gallery(self) -> list[str]:
        return self._loads(self.gallery_urls)

    @property
    def stl_extra(self) -> list[str]:
        return self._loads(self.stl_extra_urls)

    @property
    def preferred_download_url(self) -> str | None:
        if self.zip_url:
            return self.zip_url
        if self.stl_main_url:
            return self.stl_main_url
        extras = self.stl_extra
        return extras[0] if extras else None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "price": self.price,
            "tags": self.tags,
            "desc": self.desc,
            "user_id": self.user_id,
            "cover_url": self.cover_url,
            "gallery_urls": self.gallery,      # список
            "stl_main_url": self.stl_main_url,
            "stl_extra_urls": self.stl_extra,  # список
            "zip_url": self.zip_url,
            "preferred_download_url": self.preferred_download_url,
            "format": self.format,
            "rating": self.rating,
            "downloads": self.downloads,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    # ---------- аліаси для сумісності з market.py ----------
    @property
    def cover(self) -> Optional[str]:
        return self.cover_url
    @cover.setter
    def cover(self, value: Optional[str]) -> None:
        self.cover_url = value

    @property
    def file_url(self) -> Optional[str]:
        return self.stl_main_url
    @file_url.setter
    def file_url(self, value: Optional[str]) -> None:
        self.stl_main_url = value

    @property
    def url(self) -> Optional[str]:
        return self.stl_main_url

    @property
    def photos(self) -> str:
        payload: Dict[str, Any] = {"images": self.gallery, "stl": self.stl_extra}
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return '{"images": [], "stl": []}'

    @photos.setter
    def photos(self, value: str | dict | list) -> None:
        imgs: list[str] = []
        stls: list[str] = []
        try:
            data = value if isinstance(value, (dict, list)) else json.loads(value or "{}")
            if isinstance(data, list):
                imgs = [s for s in data if s]
            elif isinstance(data, dict):
                imgs = [s for s in (data.get("images") or []) if s]
                stls = [s for s in (data.get("stl") or []) if s]
        except Exception:
            imgs, stls = [], []
        self.gallery_urls = json.dumps(imgs, ensure_ascii=False)
        self.stl_extra_urls = json.dumps(stls, ensure_ascii=False)

    def __repr__(self) -> str:
        return f"<MarketItem id={self.id} title={self.title!r} price={self.price} user={self.user_id}>"

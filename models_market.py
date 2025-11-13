# models_market.py
# Моделі для STL Market: категорії, товари, обране, відгуки.
# Залежності: pip install python-slugify

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any

from slugify import slugify
from sqlalchemy import UniqueConstraint, Index, func

# ВАЖЛИВО: використовуємо спільний db та User із твого проєкту
from models import db, User  # db = той самий інстанс, User – основна юзер-модель


# ───────────────────────── Категорії ─────────────────────────

class MarketCategory(db.Model):
    __tablename__ = "market_categories"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(80), nullable=False)
    slug: str = db.Column(db.String(80), nullable=False, unique=True, index=True)

    def __repr__(self) -> str:
        return f"<MarketCategory {self.slug}>"


# ───────────────────────── Товари ────────────────────────────

class MarketItem(db.Model):
    __tablename__ = "market_items"

    id: int = db.Column(db.Integer, primary_key=True)

    # SEO/URL
    slug: str = db.Column(db.String(140), nullable=False, unique=True, index=True)

    # Основні поля
    title: str = db.Column(db.String(140), nullable=False)
    description: str = db.Column(db.Text, default="")

    # Власник
    owner_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    owner = db.relationship("User", backref="market_items", lazy="joined")

    # Категорія
    category_id: Optional[int] = db.Column(db.Integer, db.ForeignKey("market_categories.id"), index=True)
    category = db.relationship("MarketCategory", backref="items", lazy="joined")

    # Медіа
    cover_url: Optional[str] = db.Column(db.String(500))          # прев'ю
    files_json: Optional[str] = db.Column(db.Text)                 # JSON: [{url, kind, size}]

    # Ціноутворення
    price_cents: int = db.Column(db.Integer, default=0)
    is_free: bool = db.Column(db.Boolean, default=True)

    # Метрики
    rating: float = db.Column(db.Float, default=0.0)
    ratings_cnt: int = db.Column(db.Integer, default=0)
    downloads: int = db.Column(db.Integer, default=0)
    views: int = db.Column(db.Integer, default=0)

    # Дати
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_market_items_cat_created", "category_id", "created_at"),
    )

    # ── Утиліти ───────────────────────────────────────────────

    def ensure_slug(self) -> None:
        """Генерує унікальний slug із title."""
        if self.slug:
            return
        base = slugify(self.title or "item")
        stem = base[:90] or "item"
        candidate = stem
        n = 1
        # просто використовуємо MarketItem.query без всяких імпортів усередині
        while MarketItem.query.filter_by(slug=candidate).first():
            n += 1
            candidate = f"{stem}-{n}"
        self.slug = candidate

    @property
    def main_model_url(self) -> Optional[str]:
        """Повертає URL першого файлу (для viewer)."""
        import json
        try:
            arr = json.loads(self.files_json or "[]")
            return arr[0]["url"] if arr else None
        except Exception:
            return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "description": (self.description or "")[:1000],
            "owner_id": self.owner_id,
            "category_id": self.category_id,
            "cover_url": self.cover_url,
            "files_json": self.files_json,
            "price_cents": self.price_cents,
            "is_free": self.is_free,
            "rating": self.rating,
            "ratings_cnt": self.ratings_cnt,
            "downloads": self.downloads,
            "views": self.views,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<MarketItem {self.slug}>"


# ───────────────────────── Обране ────────────────────────────

class Favorite(db.Model):
    __tablename__ = "market_favorites"

    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    item_id: int = db.Column(db.Integer, db.ForeignKey("market_items.id"), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref="favorite_items")
    # важливо: повністю кваліфіковане ім’я, щоб не плутатись з models.MarketItem
    item = db.relationship("models_market.MarketItem", backref="fav_by")

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_market_fav"),
    )

    def __repr__(self) -> str:
        return f"<Fav u{self.user_id}-i{self.item_id}>"


# ───────────────────────── Відгуки ───────────────────────────

class Review(db.Model):
    __tablename__ = "market_reviews"

    id: int = db.Column(db.Integer, primary_key=True)
    item_id: int = db.Column(db.Integer, db.ForeignKey("market_items.id"), nullable=False, index=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    rating: int = db.Column(db.Integer, nullable=False)  # 1..5
    text: str = db.Column(db.Text, default="")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    item = db.relationship("models_market.MarketItem", backref="reviews")
    user = db.relationship("User")

    __table_args__ = (
        UniqueConstraint("item_id", "user_id", name="uq_market_review_once"),
    )

    def __repr__(self) -> str:
        return f"<Review item={self.item_id} user={self.user_id} r={self.rating}>"


# ──────────────────────── Хелпер рейтингу ────────────────────

def recompute_item_rating(item_id: int) -> None:
    """Перерахунок середнього рейтингу та кількості відгуків для Item."""
    row = db.session.query(
        func.coalesce(func.avg(Review.rating), 0.0),
        func.count(Review.id)
    ).filter(Review.item_id == item_id).first()

    avg = float(row[0]) if row else 0.0
    cnt = int(row[1]) if row else 0

    it = MarketItem.query.get(item_id)
    if it:
        it.rating = round(avg, 2)
        it.ratings_cnt = cnt
        db.session.commit()

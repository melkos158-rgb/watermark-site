# models.py
from __future__ import annotations

from datetime import datetime

# >>> використовуємо існуючий інстанс з db.py
from db import User as _User
from db import db as _db  # ✅ беремо і db, і User з db.py


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

# ✅ також експортуємо User як просто посилання на клас із db.py
User = _User

__all__ = ["db", "MarketItem", "User", "MarketFavorite", "MarketReview", "Favorite", "Review", "recompute_item_rating"]



# ✅ Use single canonical MarketItem model (defined in models.py)
from models import MarketItem

# ============================================================
#   ТАБЛИЦЯ УЛЮБЛЕНИХ (ДОДАВ У ПРОЕКТ — /api/market/fav легко
#   буде писати в неї)
# ============================================================

class MarketFavorite(_db.Model):
    """
    Улюблені моделі користувача.
    Один запис = один користувач + одна модель.
    """
    __tablename__ = "item_favorites"  # ⚠️ НЕ МІНЯТИ поки не перевіримо /api/_debug/favorites-schema

    id = _db.Column(_db.Integer, primary_key=True)
    user_id = _db.Column(_db.Integer, _db.ForeignKey("users.id"), index=True, nullable=False)
    item_id = _db.Column(_db.Integer, _db.ForeignKey("items.id"), index=True, nullable=False)
    created_at = _db.Column(_db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        _db.UniqueConstraint("user_id", "item_id", name="uix_fav_user_item"),
        {"extend_existing": True},  # 🔧 Дозволяє дублювання таблиць
    )

    def __repr__(self) -> str:
        return f"<MarketFavorite user={self.user_id} item={self.item_id}>"


# ============================================================
#   ТАБЛИЦЯ ВІДГУКІВ
# ============================================================

class MarketReview(_db.Model):
    """
    Відгуки та рейтинг по моделям.
    """
    __tablename__ = "item_reviews"
    __table_args__ = {"extend_existing": True}  # 🔧 Дозволяє дублювання таблиць

    id = _db.Column(_db.Integer, primary_key=True)
    item_id = _db.Column(_db.Integer, _db.ForeignKey("items.id"), index=True, nullable=False)
    user_id = _db.Column(_db.Integer, _db.ForeignKey("users.id"), index=True, nullable=False)

    rating = _db.Column(_db.Integer, default=5)  # 1–5
    text = _db.Column(_db.Text, default="")

    created_at = _db.Column(_db.DateTime, default=datetime.utcnow, index=True)
    updated_at = _db.Column(
        _db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<MarketReview item={self.item_id} user={self.user_id} rating={self.rating}>"


# ============================================================
# ALIASES FOR COMPATIBILITY
# ============================================================

# market_api.py imports "Favorite" and "Review"
Favorite = MarketFavorite
Review = MarketReview


def recompute_item_rating(item_id: int) -> None:
    """
    Recompute average rating for an item based on all reviews.
    Updates MarketItem.rating field.
    """
    from sqlalchemy import func
    avg_rating = _db.session.query(func.avg(MarketReview.rating))\
        .filter(MarketReview.item_id == item_id)\
        .scalar()
    
    item = MarketItem.query.get(item_id)
    if item:
        item.rating = float(avg_rating) if avg_rating else 0.0
        _db.session.commit()

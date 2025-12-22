from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from models import db  # ✅ MarketItem вже є

# ⚠️ Переконайся, що в models.py є модель Bundle
#   class Bundle(db.Model):
#       id, user_id, title, description, price, discount, thumb_url, is_active
#       + зв'язок item_ids / items (як тобі удобно)
try:
    from models import Bundle
except Exception:
    Bundle = None


bundles_api = Blueprint("bundles_api", __name__, url_prefix="/api/market")


def _current_user_id():
    """
    Дістаємо поточного користувача:
      - якщо ти використовуєш g.user
      - або session["user_id"]
    Підлаштуй під свою auth-схему.
    """
    uid = getattr(g, "user_id", None)
    if uid:
        return uid
    user = getattr(g, "user", None)
    if user is not None:
        return getattr(user, "id", None)
    # Якщо у тебе юзер у session:
    try:
        from flask import session
        return session.get("user_id")
    except Exception:
        return None


def _bundle_to_dict(b):
    # item_ids може зберігатися як масив або як CSV-строка в моделі
    item_ids = []
    if hasattr(b, "item_ids") and isinstance(b.item_ids, (list, tuple)):
        item_ids = list(b.item_ids)
    elif hasattr(b, "item_ids_csv"):
        raw = b.item_ids_csv or ""
        item_ids = [int(x) for x in raw.split(",") if x.strip().isdigit()]

    return {
        "id": b.id,
        "title": b.title,
        "description": getattr(b, "description", "") or "",
        "price": float(b.price or 0),
        "discount": float(getattr(b, "discount", 0) or 0),
        "thumb_url": getattr(b, "thumb_url", "") or "",
        "is_active": bool(getattr(b, "is_active", True)),
        "item_ids": item_ids,
        "items_count": len(item_ids),
    }


@bundles_api.route("/bundles", methods=["GET"])
def list_bundles():
    if Bundle is None:
        return jsonify({"ok": False, "error": "bundles_disabled"}), 501
    """
    GET /api/market/bundles
    Повертає всі бандли поточного автора.
    """
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    stmt = select(Bundle).where(Bundle.user_id == user_id)
    bundles = db.session.execute(stmt).scalars().all()

    return jsonify({
        "items": [_bundle_to_dict(b) for b in bundles]
    })


@bundles_api.route("/bundles", methods=["POST"])
def create_bundle():
    if Bundle is None:
        return jsonify({"ok": False, "error": "bundles_disabled"}), 501
    """
    POST /api/market/bundles
    JSON:
      {
        "title": "...",
        "description": "...",
        "price": 10.0,
        "discount": 20,
        "thumb_url": "https://...",
        "item_ids": [1,2,3],
        "is_active": true
      }
    """
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    price = float(data.get("price") or 0)
    discount = float(data.get("discount") or 0)
    thumb_url = (data.get("thumb_url") or "").strip()
    description = (data.get("description") or "").strip()
    is_active = bool(data.get("is_active", True))

    raw_item_ids = data.get("item_ids") or []
    item_ids: list[int] = []
    for x in raw_item_ids:
        try:
            item_ids.append(int(x))
        except (TypeError, ValueError):
            continue

    b = Bundle(
        user_id=user_id,
        title=title,
        description=description,
        price=price,
        discount=discount,
        thumb_url=thumb_url,
        is_active=is_active,
    )

    # Зберігаємо item_ids
    if hasattr(b, "item_ids"):
        b.item_ids = item_ids
    elif hasattr(b, "item_ids_csv"):
        b.item_ids_csv = ",".join(str(i) for i in item_ids)

    db.session.add(b)
    db.session.commit()

    return jsonify({"item": _bundle_to_dict(b)}), 201


@bundles_api.route("/bundles/<int:bundle_id>", methods=["PUT", "PATCH"])
def update_bundle(bundle_id: int):
    if Bundle is None:
        return jsonify({"ok": False, "error": "bundles_disabled"}), 501
    """
    PUT /api/market/bundles/<id>
    PATCH /api/market/bundles/<id>
    """
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    b = db.session.get(Bundle, bundle_id)
    if not b or b.user_id != user_id:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json(silent=True) or {}

    if "title" in data:
        b.title = (data["title"] or "").strip()
    if "description" in data:
        b.description = (data["description"] or "").strip()
    if "price" in data:
        try:
            b.price = float(data["price"])
        except (TypeError, ValueError):
            pass
    if "discount" in data:
        try:
            b.discount = float(data["discount"])
        except (TypeError, ValueError):
            pass
    if "thumb_url" in data:
        b.thumb_url = (data["thumb_url"] or "").strip()
    if "is_active" in data:
        b.is_active = bool(data["is_active"])

    if "item_ids" in data:
        raw_item_ids = data.get("item_ids") or []
        item_ids: list[int] = []
        for x in raw_item_ids:
            try:
                item_ids.append(int(x))
            except (TypeError, ValueError):
                continue

        if hasattr(b, "item_ids"):
            b.item_ids = item_ids
        elif hasattr(b, "item_ids_csv"):
            b.item_ids_csv = ",".join(str(i) for i in item_ids)

    db.session.commit()

    return jsonify({"item": _bundle_to_dict(b)})


@bundles_api.route("/bundles/<int:bundle_id>", methods=["DELETE"])
def delete_bundle(bundle_id: int):
    if Bundle is None:
        return jsonify({"ok": False, "error": "bundles_disabled"}), 501
    """
    DELETE /api/market/bundles/<id>
    """
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    b = db.session.get(Bundle, bundle_id)
    if not b or b.user_id != user_id:
        return jsonify({"error": "not_found"}), 404

    db.session.delete(b)
    db.session.commit()

    return jsonify({"ok": True})

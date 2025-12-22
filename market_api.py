
import os

from flask import (abort, current_app, jsonify, request, send_from_directory,
                   session)
from sqlalchemy import desc

from market_api_full import bp  # noqa: F401
from models import MarketItem


def _auth_required():
    return jsonify({"ok": False, "error": "auth_required"}), 401


@bp.get("/my/items")
def my_items():
    uid = session.get("user_id")
    if not uid:
        return _auth_required()

    page = int(request.args.get("page", 1) or 1)
    per_page = int(request.args.get("per_page", 24) or 24)
    per_page = max(1, min(per_page, 100))

    q = MarketItem.query.filter(MarketItem.user_id == uid).order_by(desc(MarketItem.created_at))
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()

    def _safe_json(it):
        return {
            "id": it.id,
            "title": getattr(it, "title", "") or "",
            "price": getattr(it, "price", 0) or 0,
            "cover_url": getattr(it, "cover_url", None),
            "gallery_urls": getattr(it, "gallery_urls", "[]") or "[]",
            "created_at": getattr(it, "created_at", None).isoformat() if getattr(it, "created_at", None) else None,
        }

    return jsonify({
        "ok": True,
        "page": page,
        "per_page": per_page,
        "total": total,
        "items": [_safe_json(x) for x in items],
    })


@bp.get("/media/<int:item_id>/<path:filename>")
def market_media(item_id, filename):
    root = current_app.config.get("MEDIA_ROOT")
    if not root:
        abort(404)
    return send_from_directory(os.path.join(root, str(item_id)), filename)

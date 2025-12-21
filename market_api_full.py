# === LEGACY COMPAT: GET /api/my/items ===
@bp.get("/my/items")
def api_my_items():
    from flask import session, jsonify, request
    from models_market import MarketItem
    uid = session.get("user_id")
    if not uid:
        return jsonify(ok=False, error="auth_required"), 401
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 24))
    q = MarketItem.query.filter_by(user_id=uid)
    total = q.count()
    pages = (total + per_page - 1) // per_page
    items = q.order_by(MarketItem.id.desc()).offset((page-1)*per_page).limit(per_page).all()
    def serialize_item(it):
        return {
            "id": it.id,
            "title": getattr(it, "title", None),
            "price": getattr(it, "price", None),
            "cover_url": getattr(it, "cover_url", None),
        }
    return jsonify(ok=True, items=[serialize_item(it) for it in items], page=page, pages=pages, total=total)

# === SERVE MEDIA FILES: /api/market/media/<id>/<filename> ===
@bp.get("/media/<int:item_id>/<path:filename>")
def api_market_media(item_id, filename):
    import os
    from flask import current_app, send_from_directory, abort
    root = current_app.config.get("UPLOADS_ROOT") or "/data/market_uploads"
    item_dir = os.path.join(root, str(item_id))
    file_path = os.path.join(item_dir, filename)
    if not os.path.isfile(file_path):
        abort(404)
    return send_from_directory(item_dir, filename)
from flask import Blueprint

bp = Blueprint("market_api", __name__)

# === DIAGNOSTIC PING ENDPOINT ===
@bp.get("/ping")
def ping():
    from flask import current_app
    ep = None
    methods = None
    for r in current_app.url_map.iter_rules():
        if r.rule == "/market/upload":
            ep = r.endpoint
            methods = sorted(list(r.methods))
            break

    return jsonify(
        ok=True,
        route="/api/market/ping",
        market_upload_endpoint=ep,
        market_upload_methods=methods,
    )

from flask import Blueprint, request, jsonify, current_app, url_for, abort, session
from models_market import db, MarketItem, MarketFavorite, Favorite, Review, recompute_item_rating

bp = Blueprint("market_api", __name__, url_prefix="/api/market")

# === COMPAT GET /api/market/items ===
@bp.get("/items")
def api_market_items_compat():
    # Import and call the main /api/items handler from market.py
    from market import api_items
    return api_items()

# === LEGACY COMPAT ENDPOINT ===
@bp.post("/upload")
def api_market_upload_compat():
    """
    Legacy compat endpoint for old upload_manager.js:
    POST /api/market/upload
    Must NOT rely only on session, because draft can be created via different flow.
    """
    from flask import request, jsonify, session
    from models import MarketItem
    from db import db


    # 1) Try to get item_id from request (FormData, args, or JSON)
    item_id = (
        request.form.get("item_id")
        or request.form.get("draft_id")
        or request.form.get("id")
        or request.args.get("item_id")
        or request.args.get("draft_id")
        or request.args.get("id")
    )
    if item_id and str(item_id).isdigit():
        item_id = int(item_id)
    else:
        item_id = None

    # json body (application/json)
    if item_id is None and request.is_json:
        data = request.get_json(silent=True) or {}
        for key in ("item_id", "draft_id", "id"):
            v = data.get(key)
            if isinstance(v, int):
                item_id = v
                break
            if isinstance(v, str) and v.isdigit():
                item_id = int(v)
                break

    # session fallback
    if item_id is None:
        sid = session.get("upload_draft_id")
        if isinstance(sid, int):
            item_id = sid
        elif isinstance(sid, str) and sid.isdigit():
            item_id = int(sid)

    # 2) If still none -> create draft right here and set session
    if item_id is None:
        it = MarketItem()
        if hasattr(it, "status"):
            it.status = "draft"
        db.session.add(it)
        db.session.commit()
        session["upload_draft_id"] = it.id
        return jsonify({"ok": True, "item_id": it.id, "legacy": True, "created": True}), 200

    # Ensure session is synced
    session["upload_draft_id"] = item_id

    # 3) Validate item exists (optional but useful)
    it = MarketItem.query.get(item_id)
    if not it:
        return jsonify({"error": "draft_not_found", "item_id": item_id}), 404

    # If draft exists, do NOT fallback to legacy
    return jsonify({"ok": True, "item_id": it.id, "legacy": False, "created": False}), 200

# === REAL DRAFT ENDPOINT ===
@bp.post("/items/draft")
def api_market_items_draft():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "auth"}), 401

    # Try to find existing draft in session
    draft_id = session.get("upload_draft_id")
    it = None
    if draft_id:
        try:
            draft_id = int(draft_id)
            it = MarketItem.query.get(draft_id)
        except Exception:
            it = None
    if it:
        session["upload_draft_id"] = int(it.id)
        session.modified = True
        return jsonify({"draft": {"id": it.id}}), 200

    # Create new draft
    item = MarketItem(
        user_id=uid,
        title=""
    )
    # Set status/state fields only if they exist
    if hasattr(item, "status"):
        item.status = "draft"
    if hasattr(item, "upload_status"):
        item.upload_status = "draft"
    if hasattr(item, "upload_progress"):
        item.upload_progress = 0
    if hasattr(item, "is_published"):
        item.is_published = False

    db.session.add(item)
    db.session.commit()
    session["upload_draft_id"] = int(item.id)
    session.modified = True

    current_app.logger.info(f"[UPLOAD] Draft created: {item.id}")

    return jsonify({
        "draft": {
            "id": item.id
        }
    }), 200

# ============================================================
#  PROOFLY MARKET – MAX POWER API
#  FULL SUPPORT FOR edit_model.js AUTOSAVE + FILE UPLOAD
# ============================================================



import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

from functools import wraps
from sqlalchemy import func, text

# ...existing code from MAX POWER API section...

# ============================================================
# DEBUG ENDPOINT (TEMPORARY)
# ============================================================


@bp.get("/debug/item/<int:item_id>/files")
def debug_item_files_disk(item_id: int):
    """
    DEBUG: Show raw file URLs from database
    Use: /api/market/debug/item/41/files
    """
    it = MarketItem.query.get_or_404(item_id)
    return jsonify({
        "id": it.id,
        "stl_main_url": getattr(it, "stl_main_url", None),
        "stl_extra_urls": getattr(it, "stl_extra_urls", None),
        "zip_url": getattr(it, "zip_url", None),
        "cover_url": getattr(it, "cover_url", None),
        "gallery_urls": getattr(it, "gallery_urls", None),
    })

# ...rest of the code from the MAX POWER API section...

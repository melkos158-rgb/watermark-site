# === REAL DRAFT ENDPOINT ===
@bp.post("/items/draft")
def api_market_items_draft():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "auth"}), 401

    item = MarketItem(
        user_id=uid,
        title="",
        upload_status="draft",
        upload_progress=0,
        is_published=False,
    )
    db.session.add(item)
    db.session.commit()

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


from market_api import bp

import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

from functools import wraps
from flask import request, jsonify, current_app, url_for, abort, session
from sqlalchemy import func, text

from models_market import (
    db,
    MarketItem,
    MarketFavorite,
    Favorite,
    Review,
    recompute_item_rating,
)

# ...existing code from MAX POWER API section...

# ============================================================
# DEBUG ENDPOINT (TEMPORARY)
# ============================================================

@bp.get("/debug/item/<int:item_id>/files")
def debug_item_files_db(item_id):
    """
    🔍 DEBUG: Show raw file URLs from database
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

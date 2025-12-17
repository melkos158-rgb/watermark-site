# ============================================================
#  PROOFLY MARKET – MAX POWER API
#  FULL SUPPORT FOR edit_model.js AUTOSAVE + FILE UPLOAD
# ============================================================

from __future__ import annotations
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

from functools import wraps
from flask import Blueprint, request, jsonify, current_app, url_for, abort, session
from sqlalchemy import func, text

from models_market import (
    db,
    MarketItem,
    Favorite,
    Review,
    recompute_item_rating,
)

bp = Blueprint("market_api", __name__)

# ============================================================
# AUTH
# ============================================================

class _SessionUser:
    @property
    def is_authenticated(self):
        return bool(session.get("user_id"))

    @property
    def id(self):
        return session.get("user_id")


current_user = _SessionUser()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return _json_error("Unauthorized", 401)
        return f(*args, **kwargs)
    return wrapper


# ============================================================
# DEBUG ENDPOINTS
# ============================================================

@bp.get("/_debug/favorites-schema")
@bp.get("/_debug/favorites_schema")  # alias (дефіс vs андерскор)
def debug_favorites_schema():
    """🔍 Діагностика: які таблиці *fav* існують у БД та їх схема"""
    tables = db.session.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
          AND table_name ILIKE '%fav%';
    """)).fetchall()

    result = {}
    for (table_name,) in tables:
        cols = db.session.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name = :t
            ORDER BY ordinal_position;
        """), {"t": table_name}).fetchall()

        result[table_name] = [
            {"column": c, "type": t} for c, t in cols
        ]

    return jsonify(result)


# ============================================================
# HELPERS
# ============================================================

def _json_error(msg, status=400):
    r = jsonify({"ok": False, "error": msg})
    r.status_code = status
    return r


def _ensure_upload_dir() -> Path:
    root = Path(current_app.static_folder) / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(name: str) -> str:
    ext = os.path.splitext(name)[1]
    token = secrets.token_hex(8)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{token}{ext}"


def _save_file(file) -> Tuple[str, int]:
    """LOCAL SAVE — can be swapped with Cloudinary"""
    updir = _ensure_upload_dir()
    fname = _safe_name(file.filename or "file.bin")
    fpath = updir / fname
    file.save(fpath)
    rel = f"uploads/{fname}"
    url = url_for("static", filename=rel, _external=False)
    try:
        size = fpath.stat().st_size
    except:
        size = 0
    return url, size


def _files_json_to_list(js):
    """
    Универсальний парсер для збережених files_json / gallery_urls.
    Якщо js — JSON рядок -> повертаємо розпарсений об'єкт/список.
    Якщо вже список/об'єкт — повертаємо як є.
    """
    try:
        if js is None:
            return []
        if isinstance(js, (list, dict)):
            return js
        return json.loads(js or "[]")
    except Exception:
        return []


def _is_owner(it: MarketItem):
    return current_user.id and it.owner_id == int(current_user.id)


# ============================================================
# AUTOSAVE UPDATE ENDPOINT
# ============================================================

@bp.post("/update/<int:item_id>")
@login_required
def update_item(item_id: int):
    """
    AUTOSAVE endpoint.
    Accepts JSON:
      { "title": "...", "description": "...", "tags": "...", ... }
    """
    payload = request.get_json(silent=True) or {}
    it = MarketItem.query.get(item_id)

    if not it:
        return _json_error("Item not found", 404)

    if not _is_owner(it):
        return _json_error("Forbidden", 403)

    # Allowed fields
    allowed = {
        "title",
        "description",
        "tags",
        "category",
        "price",
        "price_cents",
        "is_free",
    }

    updated = False

    for key, val in payload.items():
        if key not in allowed:
            continue

        if key == "category":
            # TODO: MarketCategory not implemented yet
            # val = (val or "").strip()
            # cat = MarketCategory.query.filter_by(title=val).first()
            # it.category_id = cat.id if cat else None
            # updated = True
            continue

        if key == "price":
            try:
                it.price_cents = int(float(val) * 100)
                it.is_free = (it.price_cents == 0)
                updated = True
            except:
                pass
            continue

        if key == "price_cents":
            try:
                it.price_cents = int(val)
                it.is_free = (it.price_cents == 0)
                updated = True
            except:
                pass
            continue

        if key == "is_free":
            it.is_free = str(val).lower() in ("1", "true", "yes", "on")
            if it.is_free:
                it.price_cents = 0
            updated = True
            continue

        # simple string fields
        setattr(it, key, val)
        updated = True

    if updated:
        db.session.commit()

    return jsonify({"ok": True})


# ============================================================
# FILE UPLOAD /api/market/upload/<id>
# ============================================================

@bp.post("/upload/<int:item_id>")
@login_required
def upload_edit(item_id: int):
    """
    Update STL + images.
    FormData fields:
      - new_images[] (list of files)
      - stl (file)
      - (ignored) text fields — handled by autosave
    """
    it = MarketItem.query.get(item_id)
    if not it:
        return _json_error("Item not found", 404)

    if not _is_owner(it):
        return _json_error("Forbidden", 403)

    # Приводимо поточні файли до зручних структур
    files_json_raw = _files_json_to_list(it.files_json)
    # files_json_raw — може бути list[dict] або list[str]
    # gallery_urls може бути рядком JSON або список
    gallery_raw = _files_json_to_list(it.gallery_urls)

    # ======================================================
    # 1) HANDLE PHOTOS
    # ======================================================
    new_images = request.files.getlist("new_images")
    added_photos = []

    for img_file in new_images:
        if not img_file or not img_file.filename:
            continue

        url, size = _save_file(img_file)
        added_photos.append({
            "url": url,
            "kind": "image",
            "size": size
        })

    # Якщо додано нові фото — додамо у files_json та gallery_urls
    if added_photos:
        # Якщо немає обкладинки — перше додане фото стає cover
        if not it.cover_url:
            it.cover_url = added_photos[0]["url"]

        # Додаємо об'єкти у files_json (щоб зберегти мета)
        if not isinstance(files_json_raw, list):
            files_json_raw = []
        files_json_raw.extend(added_photos)

        # Додаємо чисті URL у gallery_raw (список рядків)
        if not isinstance(gallery_raw, list):
            gallery_raw = []
        gallery_raw.extend([p["url"] for p in added_photos])

    # ======================================================
    # 2) HANDLE STL (replace)
    # ======================================================
    stl_file = request.files.get("stl")

    if stl_file and stl_file.filename:
        url, size = _save_file(stl_file)
        kind = "stl"
        name = stl_file.filename.lower()
        if name.endswith(".obj"):
            kind = "obj"
        if name.endswith(".gltf") or name.endswith(".glb"):
            kind = "gltf"
        if name.endswith(".ply"):
            kind = "ply"
        if name.endswith(".zip"):
            kind = "zip"

        # Replace main file: remove old and set new as first
        files_json_raw = [f for f in files_json_raw if not (isinstance(f, dict) and f.get("kind") == "stl")]
        files_json_raw.insert(0, {
            "url": url,
            "kind": kind,
            "size": size
        })

    # ======================================================
    # 3) Записуємо назад у модель (обидва поля)
    # ======================================================
    try:
        it.files_json = json.dumps(files_json_raw, ensure_ascii=False)
    except Exception:
        # fallback: якщо не вдається серіалізувати — ігноруємо
        pass

    try:
        it.gallery_urls = json.dumps(gallery_raw, ensure_ascii=False)
    except Exception:
        pass

    # Якщо ще не задано cover_url, спробуємо взяти з gallery
    try:
        if not it.cover_url:
            g = _files_json_to_list(it.gallery_urls)
            if g and isinstance(g, list) and len(g):
                first = g[0]
                if isinstance(first, str):
                    it.cover_url = first
                elif isinstance(first, dict) and first.get("url"):
                    it.cover_url = first.get("url")
    except Exception:
        pass

    db.session.commit()

    return jsonify({"ok": True})


# ============================================================
# FAVORITE TOGGLE (Instagram-style heart save system)
# ============================================================

@bp.post("/favorite")
@login_required
def toggle_favorite():
    """
    Toggle favorite status for an item.
    Request JSON: { "item_id": 123, "on": true/false }
    Response: { "ok": true, "on": true/false }
    
    ⚠️ Uses market_favorites table (no id column) via raw SQL
    """
    # ✅ ЗАЛІЗОБЕТОННИЙ парсинг payload (fallback для різних форматів)
    payload = request.get_json(silent=True)
    
    if not payload:
        # Fallback 1: form data
        payload = request.form.to_dict()
    
    if not payload:
        # Fallback 2: raw JSON string
        try:
            import json
            payload = json.loads(request.data.decode('utf-8'))
        except Exception:
            payload = {}
    
    # 🔍 DEBUG LOG (тимчасово для діагностики)
    current_app.logger.info(
        "[FAV] 📥 REQUEST: payload=%s content_type=%s user_id=%s request.json=%s", 
        payload, 
        request.content_type,
        current_user.id,
        request.get_json(silent=True)
    )
    
    item_id = payload.get("item_id")
    on = payload.get("on", True)
    
    # 🔍 Додатковий DEBUG
    current_app.logger.info(
        "[FAV] 🔍 PARSED: item_id=%s (type=%s), on=%s (type=%s), uid=%s",
        item_id, type(item_id).__name__,
        on, type(on).__name__,
        current_user.id
    )

    if not item_id:
        current_app.logger.warning("[FAV] Missing item_id in payload=%s", payload)
        return _json_error("Missing item_id", 400)

    try:
        item_id = int(item_id)
    except (ValueError, TypeError):
        current_app.logger.warning("[FAV] Invalid item_id=%s", item_id)
        return _json_error("Invalid item_id", 400)

    # Check if item exists
    item = MarketItem.query.get(item_id)
    if not item:
        return _json_error("Item not found", 404)

    user_id = current_user.id

    try:
        if on:
            # Add to favorites - market_favorites(user_id, item_id, created_at)
            # ✅ ЗАЛІЗОБЕТОН: WHERE NOT EXISTS працює навіть без UNIQUE constraint
            db.session.execute(text("""
                INSERT INTO market_favorites (user_id, item_id, created_at)
                SELECT :user_id, :item_id, NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM market_favorites
                    WHERE user_id = :user_id AND item_id = :item_id
                )
            """), {"user_id": user_id, "item_id": item_id})
            db.session.commit()
            current_app.logger.info("[FAV] Added user=%s item=%s", user_id, item_id)
            return jsonify({"ok": True, "on": True})
        else:
            # Remove from favorites
            db.session.execute(text("""
                DELETE FROM market_favorites
                WHERE user_id = :user_id AND item_id = :item_id
            """), {"user_id": user_id, "item_id": item_id})
            db.session.commit()
            current_app.logger.info("[FAV] Removed user=%s item=%s", user_id, item_id)
            return jsonify({"ok": True, "on": False})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("[FAV] Database error: %s", e)
        return _json_error("Database error", 500)


# ============================================================
# REST of endpoints (LIST, DETAIL, FAV, REVIEW, CHECKOUT, TRACK)
# ============================================================
# (Не змінював інші ендпоінти — вони залишаються як в оригіналі)

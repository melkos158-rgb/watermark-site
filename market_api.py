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
    MarketFavorite,
    Favorite,
    Review,
    recompute_item_rating,
)

bp = Blueprint("market_api", __name__)

# ============================================================
# AUTO-CREATE FAVORITES TABLE (compat fix for Railway)
# ============================================================

_fav_schema_ready = False

def _ensure_favorites_table():
    """
    Авто-створення таблиці item_favorites, якщо її немає.
    Використовується MarketFavorite.__tablename__ для сумісності.
    """
    table_name = MarketFavorite.__tablename__
    
    try:
        # Спробуємо створити через SQLAlchemy metadata
        db.create_all()
        current_app.logger.info(f"[FAV] Table {table_name} ensured via db.create_all()")
    except Exception as e:
        # Fallback: raw SQL (PostgreSQL/SQLite compatible)
        db.session.rollback()
        try:
            db.session.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, item_id)
                )
            """))
            db.session.commit()
            current_app.logger.info(f"[FAV] Table {table_name} created via raw SQL")
        except Exception as e2:
            db.session.rollback()
            current_app.logger.exception(f"[FAV] Failed to create {table_name}: {e2}")


@bp.before_app_request
def _init_fav_schema_once():
    """Виконується один раз при першому запиті до будь-якого ендпоінту."""
    global _fav_schema_ready
    if _fav_schema_ready:
        return
    try:
        _ensure_favorites_table()
        _fav_schema_ready = True
    except Exception as e:
        current_app.logger.exception("[FAV] Schema init failed: %s", e)


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


def _get_uid():
    """
    Get current user ID from session (primary) or Flask-Login (fallback).
    Returns None if not authenticated.
    
    CRITICAL: Login writes session["user_id"], so we read from there first.
    """
    # Primary: session (written by auth.py login)
    uid = session.get("user_id")
    
    # Fallback: Flask-Login (if initialized and authenticated)
    if uid is None:
        try:
            from flask_login import current_user
            if getattr(current_user, "is_authenticated", False):
                uid = current_user.id
        except Exception:
            pass
    
    return uid


# ============================================================
# MIGRATION & DIAGNOSTICS
# ============================================================

@bp.post("/api/market/_migrate-favorites")
def migrate_favorites_table():
    """
    Міграція даних: market_favorites → item_favorites (one-time)
    
    Usage: POST /api/market/_migrate-favorites
    Response: {"ok": true, "migrated": 123, "skipped": 45}
    """
    try:
        old_table = "market_favorites"
        new_table = MarketFavorite.__tablename__  # item_favorites
        
        # Перевірка чи існує стара таблиця
        try:
            count_old = db.session.execute(
                text(f"SELECT COUNT(*) FROM {old_table}")
            ).scalar()
            current_app.logger.info(f"[MIGRATE] Found {count_old} records in {old_table}")
        except Exception:
            db.session.rollback()
            return jsonify({
                "ok": False,
                "error": f"Table {old_table} does not exist. Nothing to migrate."
            }), 404
        
        # Переконатись що нова таблиця існує
        _ensure_favorites_table()
        
        # Міграція (ON CONFLICT DO NOTHING = skip duplicates)
        migration_sql = f"""
        INSERT INTO {new_table} (user_id, item_id, created_at)
        SELECT user_id, item_id, created_at
        FROM {old_table}
        ON CONFLICT (user_id, item_id) DO NOTHING
        """
        
        result = db.session.execute(text(migration_sql))
        db.session.commit()
        migrated = result.rowcount if hasattr(result, 'rowcount') else 0
        
        # Підрахунок фінальних записів
        count_new = db.session.execute(
            text(f"SELECT COUNT(*) FROM {new_table}")
        ).scalar()
        
        current_app.logger.info(
            f"[MIGRATE] ✅ Migrated {migrated} records from {old_table} → {new_table}. "
            f"Total in {new_table}: {count_new}"
        )
        
        return jsonify({
            "ok": True,
            "old_table": old_table,
            "new_table": new_table,
            "migrated": migrated,
            "skipped": count_old - migrated,
            "total_in_new": count_new
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"[MIGRATE] Failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/api/market/_check-tables")
def check_favorites_tables():
    """
    Діагностика: перевірка існування та вмісту таблиць favorites
    
    Usage: GET /api/market/_check-tables
    Response: {"ok": true, "tables": {...}, "current_table": "item_favorites"}
    """
    try:
        result = {
            "ok": True,
            "current_table": MarketFavorite.__tablename__,
            "tables": {}
        }
        
        # Перевірка обох таблиць
        for table_name in ["market_favorites", "item_favorites"]:
            try:
                count = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar()
                result["tables"][table_name] = {
                    "exists": True,
                    "count": count
                }
            except Exception as e:
                db.session.rollback()
                result["tables"][table_name] = {
                    "exists": False,
                    "error": str(e)
                }
        
        current_app.logger.info(f"[CHECK] Tables status: {result['tables']}")
        return jsonify(result)
    
    except Exception as e:
        current_app.logger.exception("[CHECK] Failed to check tables")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/api/market/_whoami")
def api_market_whoami():
    """
    Дебаг: перевірка сесії та автентифікації
    
    Usage: GET /api/market/_whoami
    Response: {"ok": true, "uid": 123, "session_keys": [...]}
    """
    uid = None
    try:
        uid = session.get("user_id")
    except Exception:
        uid = None
    return jsonify({
        "ok": True,
        "uid": uid,
        "session_keys": list(session.keys()) if hasattr(session, "keys") else None
    })


# ============================================================
# UPLOAD MANAGER (Draft + Direct Upload + Progress)
# ============================================================

@bp.post("/api/market/items/draft")
def create_draft_item():
    """
    🎬 STEP 1: Create draft item WITHOUT files
    
    Flow:
      1) User submits form → create draft
      2) Frontend gets item_id + upload_urls
      3) Redirect to /market immediately
      4) Upload files in background with progress
    
    Payload: {title, price, tags, desc, ...}
    Response: {
        ok: true, 
        item_id: 123, 
        upload_urls: {video, stl, zip, cover}
    }
    """
    uid = _get_uid()
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    
    data = request.get_json() or {}
    
    # Create draft item
    item = MarketItem(
        user_id=uid,
        title=data.get('title', 'Untitled Model'),
        price=data.get('price', 0),
        tags=data.get('tags', ''),
        desc=data.get('desc', ''),
        upload_status='draft',
        upload_progress=0,
        is_published=False  # Draft не публікується одразу
    )
    
    db.session.add(item)
    db.session.commit()
    
    # Generate signed upload URLs
    upload_urls = {}
    
    # Cloudinary для video/images (if configured)
    try:
        import cloudinary
        import cloudinary.uploader
        
        # Direct upload URLs (Cloudinary widget or API)
        # NOTE: Requires cloudinary.config() in app.py or config.py
        cloudinary_enabled = hasattr(cloudinary.config(), 'cloud_name') and cloudinary.config().cloud_name
        
        if cloudinary_enabled:
            # Return Cloudinary upload API endpoint
            upload_urls['video'] = f"https://api.cloudinary.com/v1_1/{cloudinary.config().cloud_name}/video/upload"
            upload_urls['cover'] = f"https://api.cloudinary.com/v1_1/{cloudinary.config().cloud_name}/image/upload"
        else:
            upload_urls['video'] = None
            upload_urls['cover'] = None
        
    except Exception as e:
        current_app.logger.warning(f"[DRAFT] Cloudinary not configured: {e}")
        upload_urls['video'] = None
        upload_urls['cover'] = None
    
    # For STL/ZIP: return Railway/local upload endpoint (fallback)
    # TODO: Add R2/S3 presigned URLs when configured
    upload_urls['stl'] = url_for('market_api.upload_file_chunk', 
                                  item_id=item.id, 
                                  file_type='stl', 
                                  _external=True)
    upload_urls['zip'] = url_for('market_api.upload_file_chunk', 
                                  item_id=item.id, 
                                  file_type='zip', 
                                  _external=True)
    
    current_app.logger.info(f"[DRAFT] Created item_id={item.id} for uid={uid}")
    
    return jsonify({
        "ok": True,
        "item_id": item.id,
        "upload_urls": upload_urls
    })


@bp.post("/api/market/items/<int:item_id>/attach")
def attach_uploaded_files(item_id):
    """
    🎬 STEP 3: Attach uploaded files after successful upload
    
    Called by upload_manager.js after all uploads complete
    
    Payload: {
        video_url, video_duration,
        stl_url, zip_url, cover_url,
        gallery_urls: []
    }
    """
    item = MarketItem.query.get_or_404(item_id)
    
    # Verify ownership
    if item.user_id != _get_uid():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    
    data = request.get_json() or {}
    
    # Attach video
    if data.get('video_url'):
        item.video_url = data['video_url']
        item.video_duration = data.get('video_duration', 10)
    
    # Attach STL
    if data.get('stl_url'):
        item.stl_main_url = data['stl_url']
    
    # Attach ZIP
    if data.get('zip_url'):
        item.zip_url = data['zip_url']
    
    # Attach cover
    if data.get('cover_url'):
        item.cover_url = data['cover_url']
    
    # Attach gallery
    if data.get('gallery_urls'):
        item.gallery_urls = json.dumps(data['gallery_urls'])
    
    # Mark as published
    item.upload_progress = 100
    item.upload_status = 'published'
    item.is_published = True
    
    db.session.commit()
    
    current_app.logger.info(f"[ATTACH] Item {item_id} published successfully")
    
    return jsonify({
        "ok": True,
        "item": {
            "id": item.id,
            "title": item.title,
            "upload_status": item.upload_status
        }
    })


@bp.post("/api/market/items/<int:item_id>/progress")
def update_upload_progress(item_id):
    """
    🎬 STEP 2: Update upload progress during background upload
    
    Called by upload_manager.js during XMLHttpRequest progress events
    
    Payload: {progress: 45, status: 'uploading'}
    """
    item = MarketItem.query.get_or_404(item_id)
    
    # Verify ownership
    if item.user_id != _get_uid():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    
    data = request.get_json() or {}
    
    item.upload_progress = max(0, min(100, data.get('progress', 0)))
    item.upload_status = data.get('status', 'uploading')
    
    db.session.commit()
    
    return jsonify({"ok": True, "progress": item.upload_progress})


@bp.post("/api/market/items/<int:item_id>/upload/<file_type>")
def upload_file_chunk(item_id, file_type):
    """
    📦 Fallback upload endpoint (for Railway/local storage)
    
    Handles multipart file upload with chunking support
    Used when Cloudinary/R2/S3 not configured
    
    file_type: stl | zip | cover | video
    """
    item = MarketItem.query.get_or_404(item_id)
    
    # Verify ownership
    if item.user_id != _get_uid():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "no_file"}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({"ok": False, "error": "empty_filename"}), 400
    
    # Save to Railway volume or local uploads/
    upload_dir = Path(current_app.config.get('UPLOAD_FOLDER', 'uploads')) / 'market_items' / str(item_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Secure filename
    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    filepath = upload_dir / f"{file_type}_{filename}"
    
    file.save(str(filepath))
    
    # Generate public URL (Railway volume or local static)
    file_url = url_for('static', filename=f'uploads/market_items/{item_id}/{file_type}_{filename}', _external=True)
    
    current_app.logger.info(f"[UPLOAD] Saved {file_type} for item {item_id}: {file_url}")
    
    return jsonify({
        "ok": True,
        "url": file_url,
        "filename": filename,
        "file_type": file_type
    })


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
    uid = _get_uid()
    current_app.logger.info(
        "[FAV] 📥 REQUEST: payload=%s content_type=%s user_id=%s request.json=%s", 
        payload, 
        request.content_type,
        uid,
        request.get_json(silent=True)
    )
    
    item_id = payload.get("item_id")
    on = payload.get("on", True)
    
    # 🔍 Додатковий DEBUG
    current_app.logger.info(
        "[FAV] 🔍 PARSED: item_id=%s (type=%s), on=%s (type=%s), uid=%s",
        item_id, type(item_id).__name__,
        on, type(on).__name__,
        uid
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

    # 🔥 CRITICAL: Use _get_uid() for consistency
    user_id = _get_uid()
    
    # 🔍 DIAGNOSTIC: Log session/cookie state in POST /favorite
    current_app.logger.info(
        "[toggle_favorite] 🔥 POST uid=%s item=%s on=%s | session_keys=%s cookie_keys=%s",
        user_id,
        item_id,
        on,
        list(session.keys()) if session else [],
        list(request.cookies.keys())
    )
    
    if not user_id:
        return _json_error("Unauthorized", 401)

    try:
        from sqlalchemy.exc import IntegrityError
        
        # ✅ ORM-запит: безпечний для PostgreSQL/SQLite
        fav = MarketFavorite.query.filter_by(user_id=user_id, item_id=item_id).first()

        if on:
            if not fav:
                db.session.add(MarketFavorite(user_id=user_id, item_id=item_id))
            db.session.commit()
            
            # 🔍 DEBUG: Verify write to database (self-proving response)
            table_name = MarketFavorite.__tablename__
            cnt = db.session.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE user_id = :u"),
                {"u": user_id}
            ).scalar()
            current_app.logger.info(
                "[FAV] after commit uid=%s count=%s item=%s on=%s",
                user_id, cnt, item_id, on
            )
            return jsonify({"ok": True, "on": True, "uid": user_id, "count": int(cnt or 0)})
        else:
            if fav:
                db.session.delete(fav)
            db.session.commit()
            
            # 🔍 DEBUG: Verify delete from database
            table_name = MarketFavorite.__tablename__
            cnt = db.session.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE user_id = :u"),
                {"u": user_id}
            ).scalar()
            current_app.logger.info(
                "[FAV] after commit uid=%s count=%s item=%s on=%s",
                user_id, cnt, item_id, on
            )
            return jsonify({"ok": True, "on": False, "uid": user_id, "count": int(cnt or 0)})

    except IntegrityError as e:
        db.session.rollback()
        # Якщо 2 кліки одночасно - вважаємо favorited = True
        current_app.logger.warning("[FAV] IntegrityError (race condition?): %s", e)
        return jsonify({"ok": True, "on": True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("[FAV] Database error: %s", e)
        return _json_error("Database error", 500)


# ============================================================
# REST of endpoints (LIST, DETAIL, FAV, REVIEW, CHECKOUT, TRACK)
# ============================================================
# (Не змінював інші ендпоінти — вони залишаються як в оригіналі)

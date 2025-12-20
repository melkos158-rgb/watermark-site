

bp = Blueprint("market_api", __name__)
print(f">>> market_api LOADED: {__file__}")
# === IMPORTS ===
from flask import Blueprint, request, jsonify, current_app, session, abort
from sqlalchemy import func, text
from functools import wraps
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from db import db
from models_market import MarketItem, MarketFavorite
from upload_utils import upload_video_to_cloudinary

# === BLUEPRINT (ОДИН РАЗ!) ===
bp = Blueprint("market_api", __name__)


# === HEALTHCHECK ===
@bp.get("/ping")
def api_market_ping():
    return jsonify({"ok": True})

# === MINIMAL DRAFT ENDPOINT (debug, always 200) ===
from flask import jsonify

@bp.post("/items/draft")
def api_market_items_draft_min():
    return jsonify({"ok": True, "draft": {"id": 0}}), 200

# === ROUTES DEBUG ENDPOINT ===
@bp.get("/_routes")
def api_market_routes_debug():
    from flask import current_app
    rules = []
    for r in current_app.url_map.iter_rules():
        if r.rule.startswith("/api/market"):
            rules.append({
                "rule": r.rule,
                "methods": sorted([m for m in r.methods if m not in ("HEAD", "OPTIONS")]),
                "endpoint": r.endpoint,
            })
@bp.route("/items/draft", methods=["POST"])
@bp.route("/items/draft/", methods=["POST"])
def api_market_items_draft():
    from flask_login import current_user

    user_id = current_user.id if current_user.is_authenticated else None

    draft_id = session.get("upload_draft_id")
    if draft_id:
        it = db.session.get(MarketItem, draft_id)
        if it:
            return jsonify({"draft": {"id": it.id}}), 200

    it = MarketItem()
    it.is_draft = True
    it.status = "draft"
    if user_id:
        it.user_id = user_id

    db.session.add(it)
    db.session.commit()

    session["upload_draft_id"] = it.id
    return jsonify({"draft": {"id": it.id}}), 200
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

# Import video upload and allowed file helpers
from upload_utils import upload_video_to_cloudinary


# ============================================================
# DEBUG ENDPOINT (TEMPORARY)
# ============================================================

@bp.get("/debug/item/<int:item_id>/files")
def debug_item_files(item_id):
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

# ============================================================
# UPLOADS BASE PATH HELPER
# ============================================================

def _get_uploads_base() -> Path:
    """
    Get unified base path for uploads.
    Priority: UPLOADS_ROOT (Railway volume) → UPLOAD_FOLDER → 'uploads'
    """
    base = current_app.config.get('UPLOADS_ROOT') or current_app.config.get('UPLOAD_FOLDER', 'uploads')
    return Path(base)

# ============================================================
# COLUMN MIGRATION HELPERS
# ============================================================

_column_cache = {}

def _has_column(table: str, column: str) -> bool:
    """
    Check if column exists in table (PostgreSQL).
    Cached to avoid repeated DB queries.
    """
    cache_key = f"{table}.{column}"
    
    if cache_key in _column_cache:
        return _column_cache[cache_key]
    
    try:
        result = db.session.execute(
            text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = :table AND column_name = :column
            """),
            {"table": table, "column": column}
        ).first()
        exists = result is not None
        _column_cache[cache_key] = exists
        return exists
    except Exception as e:
        current_app.logger.warning(f"[schema] Column check failed for {table}.{column}: {e}")
        _column_cache[cache_key] = False
        return False


def _ensure_items_upload_columns():
    """
    Auto-migration: Add upload-related columns if they don't exist.
    Safe, idempotent, PostgreSQL only.
    """
    try:
        items_table = "items"
        columns_added = []
        
        # video_url TEXT
        if not _has_column(items_table, "video_url"):
            db.session.execute(text(f"ALTER TABLE {items_table} ADD COLUMN video_url TEXT"))
            db.session.commit()
            columns_added.append("video_url")
            current_app.logger.info(f"[schema] add column {items_table}.video_url")
        
        # video_duration INTEGER
        if not _has_column(items_table, "video_duration"):
            db.session.execute(text(f"ALTER TABLE {items_table} ADD COLUMN video_duration INTEGER"))
            db.session.commit()
            columns_added.append("video_duration")
            current_app.logger.info(f"[schema] add column {items_table}.video_duration")
        
        # upload_status TEXT DEFAULT 'published'
        if not _has_column(items_table, "upload_status"):
            db.session.execute(text(f"ALTER TABLE {items_table} ADD COLUMN upload_status TEXT DEFAULT 'published'"))
            db.session.commit()
            columns_added.append("upload_status")
            current_app.logger.info(f"[schema] add column {items_table}.upload_status")
        
        # upload_progress INTEGER DEFAULT 100
        if not _has_column(items_table, "upload_progress"):
            db.session.execute(text(f"ALTER TABLE {items_table} ADD COLUMN upload_progress INTEGER DEFAULT 100"))
            db.session.commit()
            columns_added.append("upload_progress")
            current_app.logger.info(f"[schema] add column {items_table}.upload_progress")
        
        # stl_upload_id TEXT
        if not _has_column(items_table, "stl_upload_id"):
            db.session.execute(text(f"ALTER TABLE {items_table} ADD COLUMN stl_upload_id TEXT"))
            db.session.commit()
            columns_added.append("stl_upload_id")
            current_app.logger.info(f"[schema] add column {items_table}.stl_upload_id")
        
        # zip_upload_id TEXT
        if not _has_column(items_table, "zip_upload_id"):
            db.session.execute(text(f"ALTER TABLE {items_table} ADD COLUMN zip_upload_id TEXT"))
            db.session.commit()
            columns_added.append("zip_upload_id")
            current_app.logger.info(f"[schema] add column {items_table}.zip_upload_id")
        
        # is_published BOOLEAN DEFAULT TRUE
        if not _has_column(items_table, "is_published"):
            db.session.execute(text(f"ALTER TABLE {items_table} ADD COLUMN is_published BOOLEAN DEFAULT TRUE"))
            db.session.commit()
            columns_added.append("is_published")
            current_app.logger.info(f"[schema] add column {items_table}.is_published")
        
        if columns_added:
            current_app.logger.info(f"[schema] ensured items columns ok ({len(columns_added)} added)")
        else:
            current_app.logger.info("[schema] ensured items columns ok (all exist)")
        
        # Clear cache to force re-check on next migration
        global _column_cache
        _column_cache.clear()
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"[schema] Items upload columns migration failed (may already exist): {e}")


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

@bp.post("/_migrate-favorites")
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


@bp.get("/_check-tables")
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


@bp.get("/_whoami")
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

    
    # Commit with retry on UndefinedColumn (safety for parallel/cold starts)
    try:
        db.session.commit()
    except Exception as e:
        # If INSERT fails with UndefinedColumn, retry migration once
        if "UndefinedColumn" in str(e) or "column" in str(e).lower():
            current_app.logger.warning(f"[DRAFT] INSERT failed, retrying migration: {e}")
            db.session.rollback()
            _ensure_items_upload_columns()  # Force re-check
            db.session.add(item)
            db.session.commit()
        else:
            raise
    
    # Generate upload URLs
    upload_urls = {}
    cloudinary_config = None
    
    # Safe Cloudinary detection from ENV
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    
    # Fallback: parse from CLOUDINARY_URL (cloudinary://api_key:api_secret@cloud_name)
    if not cloud_name:
        cloudinary_url = os.getenv("CLOUDINARY_URL")
        if cloudinary_url:
            try:
                # Parse cloudinary://api_key:api_secret@cloud_name
                import re
                match = re.search(r'@([^/]+)', cloudinary_url)
                if match:
                    cloud_name = match.group(1)
            except Exception:
                pass
    
    # Get unsigned preset from ENV
    unsigned_preset = os.getenv("CLOUDINARY_UNSIGNED_PRESET")
    cover_fallback = os.getenv("CLOUDINARY_COVER_FALLBACK_PRESET")
    video_fallback = os.getenv("CLOUDINARY_VIDEO_FALLBACK_PRESET")
    
    # Return Cloudinary endpoints + config if available
    if cloud_name:
        upload_urls['video'] = f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload"
        upload_urls['cover'] = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
        upload_urls['cloudinary'] = {
            "cloud_name": cloud_name,
            "unsigned_preset": unsigned_preset,
            "cover_fallback": cover_fallback,
            "video_fallback": video_fallback
        }
        
        current_app.logger.info(f"[DRAFT] Cloudinary enabled: cloud={cloud_name} preset={unsigned_preset}")
    else:
        upload_urls['video'] = None
        upload_urls['cover'] = None
        upload_urls['cloudinary'] = None
        current_app.logger.warning("[DRAFT] Cloudinary not configured")
    
    # For STL/ZIP: return Railway/local chunked upload endpoint
    upload_urls['stl'] = url_for('market_api.upload_file_chunk', 
                                  item_id=item.id, 
                                  file_type='stl')
    upload_urls['zip'] = url_for('market_api.upload_file_chunk', 
                                  item_id=item.id, 
                                  file_type='zip')
    
    current_app.logger.info(f"[DRAFT] Created item_id={item.id} for uid={uid}")
    
    return jsonify({
        "ok": True,
        "item_id": item.id,
        "upload_urls": upload_urls
    })


@bp.post("/items/<int:item_id>/attach")
def attach_uploaded_files(item_id):
    """
    🎬 STEP 3: Attach uploaded files after successful upload
    
    Called by upload_manager.js after all uploads complete
    
    Payload: {
        video_url, video_duration,
        stl_main_url, stl_extra_urls: [],
        zip_url, cover_url,
        gallery_urls: []
    }
    """
    item = MarketItem.query.get_or_404(item_id)
    
    # Verify ownership
    if item.user_id != _get_uid():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    
    data = request.get_json() or {}
    
    # ✅ DIAGNOSTIC: Log full incoming payload
    current_app.logger.info(f"[ATTACH] 📥 RAW JSON: {json.dumps(data, ensure_ascii=False)}")
    current_app.logger.warning(f"[ATTACH] item={item_id} json={data}")
    
    # ✅ Log incoming URLs for diagnosis
    current_app.logger.info(
        f"[ATTACH] item={item_id} "
        f"cover={data.get('cover_url')} "
        f"stl_main={data.get('stl_main_url')} "
        f"stl_extras={len(data.get('stl_extra_urls', []))} "
        f"zip={data.get('zip_url')} "
        f"video={data.get('video_url')}"
    )
    
    # ✅ Log all uploaded URLs for validation
    current_app.logger.info(
        f"[ATTACH] 📎 Attaching files to item {item_id}: "
        f"video={data.get('video_url') is not None} "
        f"stl={data.get('stl_url') is not None} "
        f"zip={data.get('zip_url') is not None} "
        f"cover={data.get('cover_url') is not None}"
    )
    
    # ✅ COMPAT PARSING: Handle multiple STL formats
    # Priority: stl_urls[] > stl_main_url + stl_extra_urls > stl_url (legacy)
    stl_main = None
    stl_extras = []
    
    if data.get('stl_urls') and isinstance(data['stl_urls'], list):
        # ✅ NEW: stl_urls[] array format (frontend sends all STLs in one array)
        stl_list = [url for url in data['stl_urls'] if url and str(url).strip()]
        if stl_list:
            stl_main = stl_list[0]
            stl_extras = stl_list[1:5]  # Max 4 extras
            current_app.logger.info(f"[ATTACH] 🎯 stl_urls[] format: main + {len(stl_extras)} extras")
    elif data.get('stl_main_url'):
        # ✅ EXPLICIT: stl_main_url + stl_extra_urls format
        stl_main = data['stl_main_url']
        if data.get('stl_extra_urls') and isinstance(data['stl_extra_urls'], list):
            stl_extras = [url for url in data['stl_extra_urls'] if url and str(url).strip()][:4]
        current_app.logger.info(f"[ATTACH] 🎯 explicit format: main + {len(stl_extras)} extras")
    elif data.get('stl_url'):
        # ✅ LEGACY: single stl_url field
        stl_main = data['stl_url']
        current_app.logger.info(f"[ATTACH] 🎯 legacy stl_url format")
    
    # Attach video
    if data.get('video_url'):
        item.video_url = data['video_url']
        item.video_duration = data.get('video_duration', 10)
        current_app.logger.info(f"[ATTACH]   video_url: {data['video_url'][:80]}...")
    
    # ✅ Attach main STL (from compat parsing)
    if stl_main:
        item.stl_main_url = stl_main
        current_app.logger.info(f"[ATTACH]   stl_main_url: {stl_main[:80]}...")
    
    # ✅ Attach extra STL files (from compat parsing)
    # IMPORTANT: Only update if we have data (don't clear existing extras)
    if stl_extras:
        item.stl_extra_urls = json.dumps(stl_extras)
        current_app.logger.info(f"[ATTACH]   stl_extra_urls: {len(stl_extras)} files - {stl_extras}")
    else:
        current_app.logger.info(f"[ATTACH]   stl_extra_urls: keeping existing (not clearing)")
    
    # Attach ZIP
    if data.get('zip_url'):
        item.zip_url = data['zip_url']
        current_app.logger.info(f"[ATTACH]   zip_url: {data['zip_url'][:80]}...")
    
    # Attach cover
    if data.get('cover_url'):
        item.cover_url = data['cover_url']
        current_app.logger.info(f"[ATTACH]   cover_url: {data['cover_url'][:80]}...")
    
    # Attach gallery
    if data.get('gallery_urls'):
        item.gallery_urls = json.dumps(data['gallery_urls'])
    
    # ✅ Validate: must have at least stl or zip
    has_stl = bool(
        stl_main or 
        data.get('stl_main_url') or 
        data.get('stl_url') or 
        (data.get('stl_urls') and len(data.get('stl_urls', [])) > 0)
    )
    has_zip = bool(data.get('zip_url'))
    
    if not has_stl and not has_zip:
        current_app.logger.warning(f"[ATTACH] Cannot publish item {item_id}: missing both stl and zip")
        item.upload_status = 'failed'
        item.upload_progress = 0
        db.session.commit()
        return jsonify({"ok": False, "error": "missing_files"}), 400
    
    # Mark as published
    item.upload_progress = 100
    item.upload_status = 'published'
    item.is_published = True
    
    # ✅ DIAGNOSTIC: Log what we're saving to DB
    current_app.logger.info(
        f"[ATTACH] 💾 SAVED: item={item_id} "
        f"stl_main={getattr(item, 'stl_main_url', None)[:80] if getattr(item, 'stl_main_url', None) else None}... "
        f"stl_extras={getattr(item, 'stl_extra_urls', None)}"
    )
    
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


@bp.post("/items/<int:item_id>/progress")
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


@bp.get("/media/<int:item_id>/<path:filename>")
def serve_media(item_id, filename):
    """
    🎥 Serve uploaded media files from Railway volume
    
    Usage: GET /api/market/media/123/stl_model.stl
    """
    from flask import send_from_directory
    from werkzeug.utils import secure_filename
    
    # Secure the filename to prevent directory traversal
    safe_filename = secure_filename(filename)
    
    # Use unified base path (UPLOADS_ROOT with fallback)
    base = _get_uploads_base()
    upload_dir = base / 'market_items' / str(item_id)
    
    current_app.logger.info(f"[MEDIA] base={base} item_id={item_id} filename={safe_filename}")
    
    if not upload_dir.exists():
        current_app.logger.warning(f"[MEDIA] Directory not found: {upload_dir}")
        abort(404)
    
    file_path = upload_dir / safe_filename
    
    if not file_path.exists():
        current_app.logger.warning(f"[MEDIA] File not found: {file_path}")
        abort(404)
    
    # Детальне логування для діагностики
    current_app.logger.info(
        f"[MEDIA_REQ] item={item_id} filename={safe_filename} "
        f"path={file_path} exists={file_path.exists()}"
    )
    
    current_app.logger.info(f"[MEDIA] Serving file: {file_path} (size={file_path.stat().st_size})")
    return send_from_directory(str(upload_dir), safe_filename)


@bp.get("/items/<int:item_id>/debug_files")
def debug_item_files(item_id: int):
    """
    🔍 Debug endpoint: check if files exist on disk
    
    Returns actual file paths, existence status, and sizes
    for all uploaded files (stl, zip, cover, gallery)
    
    Requires: owner or admin
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"ok": False, "error": "auth"}), 401

    it = MarketItem.query.get(item_id)
    if not it:
        return jsonify({"ok": False, "error": "not_found"}), 404
    if it.user_id != uid:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    base = _get_uploads_base()
    item_dir = os.path.join(str(base), "market_items", str(item_id))

    def _probe(url: str | None):
        if not url:
            return {"url": None, "filename": None, "path": None, "exists": False, "size": None}
        # Очікуємо /api/market/media/<id>/<filename>
        filename = url.rsplit("/", 1)[-1]
        path = os.path.join(item_dir, filename)
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else None
        return {"url": url, "filename": filename, "path": path, "exists": exists, "size": size}

    payload = {
        "ok": True,
        "item_id": item_id,
        "base": str(base),
        "item_dir": item_dir,
        "stl": _probe(it.stl_main_url),
        "zip": _probe(it.zip_url),
        "cover": _probe(it.cover_url),
        "gallery_urls": it.gallery_urls,
    }
    return jsonify(payload)


@bp.post("/items/<int:item_id>/upload/<file_type>")
def upload_file_chunk(item_id, file_type):
    """
    📦 Chunked upload endpoint (for Railway/local storage)
    
    Handles large file uploads in chunks (8MB each)
    Used when Cloudinary/R2/S3 not configured
    
    Headers:
      X-Upload-Id: unique upload session ID (uuid)
      X-Chunk-Index: 0-based chunk number
      X-Chunk-Total: total number of chunks
      X-File-Name: original filename
    
    file_type: stl | zip | cover | video
    
    Response (in progress):
      {"ok": true, "done": false, "received": 3, "total": 20}
    
    Response (completed):
      {"ok": true, "done": true, "url": "..."}
    """
    item = MarketItem.query.get_or_404(item_id)
    
    # Verify ownership
    if item.user_id != _get_uid():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    
    # Validate file_type
    allowed_types = ['stl', 'zip', 'cover', 'video']
    if file_type not in allowed_types:
        return jsonify({"ok": False, "error": f"invalid_file_type, allowed: {allowed_types}"}), 400
    
    # Check for chunked upload headers
    upload_id = request.headers.get('X-Upload-Id')
    chunk_index = request.headers.get('X-Chunk-Index')
    chunk_total = request.headers.get('X-Chunk-Total')
    original_filename = request.headers.get('X-File-Name')
    
    # Simple upload (no chunking)
    if not upload_id or not chunk_index or not chunk_total:
        if 'file' not in request.files:
            return jsonify({"ok": False, "error": "no_file"}), 400
        
        file = request.files['file']
        if not file.filename:
            return jsonify({"ok": False, "error": "empty_filename"}), 400
        
        # Use unified base path (UPLOADS_ROOT with fallback)
        base = _get_uploads_base()
        upload_dir = base / 'market_items' / str(item_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        current_app.logger.info(f"[UPLOAD] base={base} item_id={item_id} file_type={file_type}")
        
        # Secure filename with timestamp for uniqueness
        from werkzeug.utils import secure_filename
        import time
        timestamp = int(time.time() * 1000)  # milliseconds
        base_filename = secure_filename(file.filename)
        filename = f"{timestamp}_{base_filename}"
        filepath = upload_dir / f"{file_type}_{filename}"
        
        file.save(str(filepath))
        
        # Generate public URL via media endpoint
        file_url = url_for('market_api.serve_media', 
                          item_id=item_id, 
                          filename=f"{file_type}_{filename}", 
                          _external=False)
        
        current_app.logger.info(f"[UPLOAD] Saved {file_type} for item {item_id}: {file_url}")
        
        # Детальне логування для діагностики
        current_app.logger.info(
            f"[UPLOAD_SAVE] item={item_id} type={file_type} "
            f"path={filepath} exists={filepath.exists()} "
            f"size={filepath.stat().st_size if filepath.exists() else None}"
        )
        
        return jsonify({
            "ok": True,
            "done": True,
            "url": file_url,
            "filename": filename,
            "file_type": file_type
        })
    
    # Chunked upload
    try:
        chunk_index = int(chunk_index)
        chunk_total = int(chunk_total)
    except ValueError:
        return jsonify({"ok": False, "error": "invalid_chunk_headers"}), 400
    
    # Use unified base path (UPLOADS_ROOT with fallback)
    base = _get_uploads_base()
    upload_dir = base / 'market_items' / str(item_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    current_app.logger.info(f"[CHUNK] base={base} item_id={item_id} file_type={file_type} chunk={chunk_index+1}/{chunk_total}")
    
    # Write chunk to .part file
    part_file = upload_dir / f"{file_type}_{upload_id}.part"
    
    # Append chunk bytes (order matters!)
    chunk_data = request.get_data()
    
    try:
        with open(part_file, 'ab') as f:
            f.write(chunk_data)
        
        # Detailed chunk upload log
        current_app.logger.info(
            f"[CHUNK] 📦 item_id={item_id} file_type={file_type} upload_id={upload_id} "
            f"chunk={chunk_index+1}/{chunk_total} bytes_received={len(chunk_data)} "
            f"filename={original_filename or 'unknown'}"
        )
        
        # Check if this is the last chunk
        if chunk_index == chunk_total - 1:
            # Finalize: rename to final filename with timestamp for uniqueness
            from werkzeug.utils import secure_filename
            import time
            timestamp = int(time.time() * 1000)  # milliseconds
            base_filename = secure_filename(original_filename or f"{file_type}_file")
            final_filename = f"{timestamp}_{base_filename}"
            final_path = upload_dir / f"{file_type}_{final_filename}"
            
            # Move .part to final location
            part_file.rename(final_path)
            
            # Generate public URL via media endpoint
            file_url = url_for('market_api.serve_media', 
                              item_id=item_id, 
                              filename=f"{file_type}_{final_filename}", 
                              _external=False)
            
            current_app.logger.info(
                f"[CHUNK] ✅ Upload completed: item={item_id} type={file_type} url={file_url}"
            )
            
            # Детальне логування для діагностики
            current_app.logger.info(
                f"[UPLOAD_SAVE] item={item_id} type={file_type} "
                f"path={final_path} exists={final_path.exists()} "
                f"size={final_path.stat().st_size if final_path.exists() else None}"
            )
            
            return jsonify({
                "ok": True,
                "done": True,
                "url": file_url,
                "filename": final_filename,
                "received": chunk_total,
                "total": chunk_total
            })
        else:
            # More chunks expected
            return jsonify({
                "ok": True,
                "done": False,
                "received": chunk_index + 1,
                "total": chunk_total
            })
    
    except Exception as e:
        current_app.logger.exception(f"[CHUNK] Error writing chunk: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


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


# ============================================================
# FILE UPLOAD /api/market/upload (legacy create handler)
# ============================================================
@bp.post("/upload")
@login_required
def upload_model():
    """
    Legacy model upload handler (create new model with files/images/video)
    FormData fields:
      - new_images[] (list of files)
      - stl (file)
      - video_file (file, optional)
      - (ignored) text fields — handled by autosave
    """
    # Parse form fields
    title = request.form.get("title", "Untitled Model")
    price = request.form.get("price", 0)
    tags = request.form.get("tags", "")
    desc = request.form.get("desc", "")
    uid = _get_uid()
    if not uid:
        return _json_error("Unauthorized", 401)

    # Create new MarketItem
    item = MarketItem(
        user_id=uid,
        title=title,
        price=price,
        tags=tags,
        desc=desc,
        upload_status='published',
        upload_progress=100,
        is_published=True
    )

    # Handle images
    files_json_raw = []
    gallery_raw = []
    new_images = request.files.getlist("new_images")
    for img_file in new_images:
        if not img_file or not img_file.filename:
            continue
        url, size = _save_file(img_file)
        files_json_raw.append({
            "url": url,
            "kind": "image",
            "size": size
        })
        gallery_raw.append(url)
    if files_json_raw and not item.cover_url:
        item.cover_url = files_json_raw[0]["url"]

    # Handle STL
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
        files_json_raw.insert(0, {
            "url": url,
            "kind": kind,
            "size": size
        })

    # Handle video upload
    video_file = request.files.get("video_file")
    if video_file and video_file.filename:
        ext = video_file.filename.rsplit(".", 1)[-1].lower()
        allowed_exts = {"mp4", "webm", "mov"}
        if ext not in allowed_exts:
            return _json_error("Invalid video format. Allowed: mp4, webm, mov", 400)
        try:
            video_url = upload_video_to_cloudinary(video_file)
            item.video_url = video_url
        except Exception as e:
            current_app.logger.exception(f"[UPLOAD] Video upload failed: {e}")
            return _json_error("Video upload failed. Please try again.", 500)

    # Save files_json and gallery_urls
    try:
        item.files_json = json.dumps(files_json_raw, ensure_ascii=False)
    except Exception:
        pass
    try:
        item.gallery_urls = json.dumps(gallery_raw, ensure_ascii=False)
    except Exception:
        pass
    if not item.cover_url and gallery_raw:
        item.cover_url = gallery_raw[0]

    db.session.add(item)
    db.session.commit()

    return jsonify({"ok": True, "item_id": item.id, "video_url": getattr(item, "video_url", None)})


# ============================================================
# FAVORITE TOGGLE (Instagram-style heart save system)
# ============================================================

@bp.post("/favorite")
def toggle_favorite():
    """
    Toggle favorite status for an item.
    Request JSON: { "item_id": 123, "on": true/false }
    Response: { "ok": true, "on": true/false }
    
    ✅ Uses session-based auth (compatible with both Flask-Login and session auth)
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
# COMPAT ENDPOINTS (prevent 404 errors in console)
# ============================================================

@bp.get("/items/<int:item_id>/printability")
def compat_printability(item_id):
    """
    Compatibility endpoint: /api/market/items/<id>/printability
    Redirects to main endpoint or returns safe default
    """
    # Check if main endpoint exists in market.py
    try:
        from flask import current_app
        # Try to find the real endpoint
        if hasattr(current_app, 'view_functions'):
            real_endpoint = current_app.view_functions.get('market.api_printability')
            if real_endpoint:
                # Call the real function
                return real_endpoint(item_id)
    except Exception:
        pass
    
    # Safe fallback: return empty data
    return jsonify({
        "ok": True,
        "data": None,
        "message": "Printability analysis not available"
    })


@bp.post("/checkout")
def compat_checkout():
    """
    Compatibility endpoint: POST /api/market/checkout
    Returns not implemented (prevents 404)
    """
    current_app.logger.warning("[CHECKOUT] Endpoint not implemented yet")
    return jsonify({
        "ok": False,
        "error": "not_implemented",
        "message": "Checkout will be available soon"
    }), 501


# ============================================================
# REST of endpoints (LIST, DETAIL, FAV, REVIEW, TRACK)
# ============================================================
# (Не змінював інші ендпоінти — вони залишаються як в оригіналі)

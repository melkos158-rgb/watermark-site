from flask import Blueprint, jsonify, session, request, redirect, url_for, flash, render_template, current_app, send_from_directory, abort, g, make_response
from flask_login import login_required, current_user
from sqlalchemy import text, bindparam, exc as sa_exc
from werkzeug.utils import secure_filename
import os
import math
import json
import shutil
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List

def _fetch_item_with_author(query):
    return query

bp = Blueprint("market", __name__)
# Always define MarketCategory (even if import fails)
try:
    from models_market import MarketCategory
except Exception:
    MarketCategory = None








# --- Далі йде твій робочий код, імпорти, функції, view-роути тощо ---




# ✅ Cloudinary (хмарне зберігання)
# Працює, якщо в ENV є CLOUDINARY_URL=cloudinary://<key>:<secret>@<cloud_name>
try:
    import cloudinary
    import cloudinary.uploader

    _CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
    if _CLOUDINARY_URL:
        cloudinary.config(cloudinary_url=_CLOUDINARY_URL)
    _CLOUDINARY_READY = bool(_CLOUDINARY_URL)
except Exception:
    _CLOUDINARY_READY = False


# ✅ беремо db та модель з models.py
from models import db, MarketItem, MarketReview, UserFollow
# ✅ MarketFavorite беремо з models_market (так як і в market_api.py)
from models_market import MarketFavorite
# якщо User у тебе лишається в db.py — імпортуємо тільки його звідти
from db import User

# ✅ категорії з нового market-модуля (safe import)
try:
    from models_market import MarketCategory
except Exception:
    MarketCategory = None




















# ✅ назву таблиці тепер беремо з моделі (fallback на "items" якщо що)
ITEMS_TBL = getattr(MarketItem, "__tablename__", "items") or "items"
USERS_TBL = getattr(User, "__tablename__", "users") or "users"
FAVORITES_TBL = getattr(MarketFavorite, "__tablename__", "item_favorites") or "item_favorites"  # 🔥 CRITICAL: item_favorites, NOT market_favorites

# Default fallback upload dir (legacy static)
LEGACY_STATIC_UPLOADS = os.path.join("static", "market_uploads")
os.makedirs(LEGACY_STATIC_UPLOADS, exist_ok=True)

ALLOWED_MODEL_EXT = {".stl", ".obj", ".ply", ".gltf", ".glb"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_ARCHIVE_EXT = {".zip"}

COVER_PLACEHOLDER = "/static/img/placeholder_stl.jpg"


def _resolve_stl_filesystem_path(url: str) -> Optional[str]:
    # Handle /media/... → uploads_root
    if url.startswith("/media/"):
        rel = url[len("/media/"):].lstrip("/")
        path = os.path.join(_uploads_root(), rel)
        return path if os.path.isfile(path) else None
    
    # Handle /static/market_uploads/... → legacy static
    if url.startswith("/static/market_uploads/"):
        rel = url[len("/static/market_uploads/"):].lstrip("/")
        path = os.path.join(current_app.root_path, "static", "market_uploads", rel)
        return path if os.path.isfile(path) else None
    
    return None


def _get_uid() -> Optional[int]:
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
            if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                uid = current_user.id
        except (ImportError, AttributeError, RuntimeError):
            pass
    
    return uid


def _is_authenticated() -> bool:
    """Check if user is authenticated (via Flask-Login or session)."""
    return _get_uid() is not None


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert SQLAlchemy Row to dict, safe for None and edge cases"""
    if row is None:
        return {}
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    try:
        return dict(row)
    except Exception:
        return {}


def _parse_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return default


def _is_missing_column_error(e: Exception) -> bool:
    """Check if exception is due to missing column in DB"""
    msg = str(e).lower()
    return (
        "no such column" in msg
        or "does not exist" in msg
        or "undefinedcolumn" in msg
        or "unknown column" in msg
    )


def _is_missing_table_error(e: Exception) -> bool:
    """Check if exception is due to missing table in DB (e.g. item_makes)"""
    msg = str(e).lower()
    return (
        "no such table" in msg  # SQLite: no such table: item_makes
        or 'relation "item_makes" does not exist' in msg  # PostgreSQL
        or "table 'item_makes' doesn't exist" in msg  # MySQL
        or "item_makes" in msg and "does not exist" in msg  # Generic Postgres pattern
    )


def _normalize_free(value: Optional[str]) -> str:
    v = (value or "all").lower()
    return v if v in ("all", "free", "paid") else "all"


# Cache for column existence checks (avoid repeated DB queries)
_column_cache = {}

def _has_column(table: str, column: str) -> bool:
    """
    Check if column exists in table.
    Cached to avoid repeated DB queries.
    
    Supports PostgreSQL (information_schema) and SQLite (PRAGMA).
    """
    cache_key = f"{table}.{column}"
    
    if cache_key in _column_cache:
        return _column_cache[cache_key]
    
    try:
        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            # PostgreSQL: query information_schema.columns
            result = db.session.execute(
                text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = :table AND column_name = :column
                """),
                {"table": table, "column": column}
            ).first()
            exists = result is not None
        else:
            # SQLite: use PRAGMA table_info
            result = db.session.execute(
                text(f"PRAGMA table_info({table})")
            ).fetchall()
            # PRAGMA returns: (cid, name, type, notnull, dflt_value, pk)
            column_names = [row[1] for row in result]
            exists = column in column_names
        _column_cache[cache_key] = exists
        return exists
    except Exception as e:
        current_app.logger.warning(f"Column check failed for {table}.{column}: {e}")
        # Assume column doesn't exist if check fails
        _column_cache[cache_key] = False
        return False


# ======================================================================
# SORTING: "Top by Real Prints" Feature + Trending Prints
# ======================================================================
# Сортування "prints" ранжує моделі за кількістю реальних роздрукувань
# (item_makes.item_id → COUNT), показуючи найбільш перевірені/популярні моделі.
#
# Trending Prints (prints_7d / prints_30d):
# - prints_7d: моделі з найбільшою кількістю роздрукувань за останні 7 днів
# - prints_30d: моделі з найбільшою кількістю роздрукувань за останні 30 днів
# - WHERE created_at >= cutoff (PostgreSQL: NOW() - INTERVAL, SQLite: datetime('now', '-N days'))
#
# Реалізація:
# 1. _normalize_sort() приймає "prints", "prints_7d", "prints_30d" як валідні значення
# 2. api_items() робить LEFT JOIN на агрегований підзапит item_makes:
#    SELECT item_id, COUNT(*) AS prints_count FROM item_makes GROUP BY item_id
# 3. Додає prints_count до SELECT та ORDER BY prints_count DESC
# 4. Fallback: якщо таблиця item_makes відсутня → prints_count = 0
# 5. _item_to_dict() повертає prints_count у JSON відповіді
# 6. Frontend: option "Top prints" у _filters.html, бейдж 🖨️ на картках
# ======================================================================

def _normalize_sort(value: Optional[str]) -> str:
    v = (value or "new").lower()
    return v if v in ("new", "price_asc", "price_desc", "downloads", "prints", "prints_7d", "prints_30d") else "new"


def _uploads_root() -> str:
    """
    Deterministic uploads root:
    - Prefer app.config['UPLOADS_ROOT'] if set
    - Else prefer environment UPLOADS_ROOT
    - Else fallback to <app_root>/static/market_uploads (legacy)
    """
    # prefer explicit config
    root = current_app.config.get("UPLOADS_ROOT") or os.environ.get("UPLOADS_ROOT")
    if root:
        # make sure it's absolute if it was relative
        if not os.path.isabs(root):
            root = os.path.abspath(root)
        return root

    # default to app.static folder legacy location
    return os.path.join(current_app.root_path, "static", "market_uploads")


def _local_media_exists(media_url: str) -> bool:
    """
    Accepts both /media/... and /static/market_uploads/... URLs.
    Checks existence in configured uploads root and legacy static path.
    """
    if not media_url:
        return False

    rel = None
    if media_url.startswith("/media/"):
        rel = media_url[len("/media/"):].lstrip("/")
    elif media_url.startswith("/static/market_uploads/"):
        rel = media_url[len("/static/market_uploads/"):].lstrip("/")
    elif media_url.startswith("media/"):
        rel = media_url[len("media/"):].lstrip("/")
    elif media_url.startswith("static/market_uploads/"):
        rel = media_url[len("static/market_uploads/"):].lstrip("/")
    else:
        # If path looks like "uploads/..." or "market_uploads/..." or a bare filename
        if media_url.startswith("uploads/") or media_url.startswith("market_uploads/"):
            rel = media_url.split("/", 1)[1] if "/" in media_url else media_url
        else:
            return False

    # check configured root
    abs_path = os.path.join(_uploads_root(), rel)
    if os.path.isfile(abs_path):
        return True

    # legacy path
    legacy = os.path.join(current_app.root_path, "static", "market_uploads", rel)
    return os.path.isfile(legacy)


def _normalize_cover_url(url: Optional[str]) -> str:
    """
    Return a normalized URL for cover:
      - keep absolute http(s)/data as-is
      - accept /media/... as-is
      - translate old /static/market_uploads/... -> /media/<rest>
      - accept /static/... as-is (e.g., /static/img/...)
      - accept 'uploads/...', 'market_uploads/...' or plain filenames -> prefix with /media/
      - otherwise return placeholder
    """
    u = (url or "").strip()
    if not u:
        return COVER_PLACEHOLDER

    if u.startswith(("http://", "https://", "data:")):
        return u

    # already our media path
    if u.startswith("/media/") or u.startswith("media/"):
        return u if u.startswith("/") else "/" + u

    # legacy static uploads -> convert to /media/
    if u.startswith("/static/market_uploads/"):
        rest = u[len("/static/market_uploads/"):].lstrip("/")
        return f"/media/{rest}"

    if u.startswith("static/market_uploads/"):
        rest = u[len("static/market_uploads/"):].lstrip("/")
        return f"/media/{rest}"

    # explicit static file (images/icons etc) -> keep absolute root-relative
    if u.startswith("/static/") or u.startswith("static/"):
        return u if u.startswith("/") else "/" + u

    # uploads or market_uploads without leading slash -> map to /media/
    if u.startswith("uploads/") or u.startswith("market_uploads/"):
        return f"/media/{u.split('/',1)[1] if '/' in u else u}"

    # bare filename or relative path -> prefix with /media/
    if "/" not in u and "." in u:
        return f"/media/{u}"

    # fallback: try to make it root-relative
    return "/" + u.lstrip("/")


def _save_upload(file_storage, subdir: str, allowed_ext: set) -> Optional[str]:
    """
    Save uploaded FileStorage into UPLOADS_ROOT (preferred) or fallback to legacy static path.
    Returns URL in form /media/<subdir>/<filename> or None.
    
    IMPORTANT: 3D model files (STL, OBJ, etc.) are ALWAYS saved locally to enable
    printability analysis. Only images can use Cloudinary.
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in allowed_ext:
        return None

    base_name = secure_filename(os.path.basename(file_storage.filename)) or ("file" + ext)
    unique_name = f"{os.path.splitext(base_name)[0]}_{uuid.uuid4().hex}{ext}"

    # ⚠️ CRITICAL: 3D models MUST be saved locally for proof score analysis
    # Skip Cloudinary for STL, OBJ, PLY, GLTF, GLB, 3MF
    is_3d_model = ext in {".stl", ".obj", ".ply", ".gltf", ".glb", ".3mf"}

    # Try cloudinary ONLY for images (not 3D models)
    if _CLOUDINARY_READY and not is_3d_model:
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            folder = f"proofly/market/{subdir}".replace("\\", "/")

            # важливо: якщо stream вже читався — повернемось на 0
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                file_storage.stream.seek(0)
            except Exception:
                pass

            if ext in ALLOWED_IMAGE_EXT:
                res = cloudinary.uploader.upload(
                    file_storage,
                    folder=folder,
                    public_id=os.path.splitext(unique_name)[0],
                    overwrite=False,
                )
            else:
                res = cloudinary.uploader.upload(
                    file_storage,
                    folder=folder,
                    resource_type="raw",
                    public_id=os.path.splitext(unique_name)[0],
                    overwrite=False,
                )

            url = res.get("secure_url") or res.get("url")
            if url:
                return url
        except Exception as _e:
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                current_app.logger.warning(
                    f"Cloudinary upload failed, fallback to local: {type(_e).__name__}: {_e}"
                )
            except Exception:
                pass

    # Preferred root from config/env
    root = _uploads_root()
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        folder = os.path.join(root, subdir)
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, unique_name)
        file_storage.save(dst)
        # Return /media/... URL
        subdir_clean = subdir.replace("\\", "/").strip("/")
        return f"/media/{subdir_clean}/{unique_name}"
    except Exception:
        # fallback to legacy static/uploads within app if preferred root fails
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            legacy_root = os.path.join(current_app.root_path, "static", "market_uploads")
            folder = os.path.join(legacy_root, subdir)
            os.makedirs(folder, exist_ok=True)
            dst = os.path.join(folder, unique_name)
            file_storage.save(dst)
            subdir_clean = subdir.replace("\\", "/").strip("/")
            # even though file saved in legacy location, return /media/ path to keep URLs consistent
            return f"/media/{subdir_clean}/{unique_name}"
        except Exception:
            current_app.logger.exception("Failed to save upload to preferred and legacy paths")
            return None


def json_dumps_safe(obj) -> str:
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "[]"


def _safe_json_list(value) -> list:
    """
    Safely parse JSON string/list to list, never crashes.
    Handles NULL, empty strings, invalid JSON, already-parsed lists.
    """
    if not value:
        return []
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        if isinstance(value, list):
            return value
        return json.loads(value) if value else []
    except Exception:
        return []


def _item_to_dict(it: Dict[str, Any]) -> Dict[str, Any]:
    """
    Universal item serialization with consistent cover_url normalization.
    Use this for all API responses to avoid cover/preview mismatches.
    """
    # Universal accessor for dict or SQLAlchemy Row
    if hasattr(it, "_mapping"):
        m = it._mapping
    else:
        m = it
    
    # Safe get helper
    def safe_get(key, default=None):
        if hasattr(m, "get"):
            return m.get(key, default)
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            return m[key] if key in m else default
        except (KeyError, TypeError):
            return default
    
    # Get cover from cover_url or cover field
    raw_cover = safe_get("cover_url") or safe_get("cover") or ""
    
    # Parse gallery_urls (may be JSON string or list) - SAFE parsing
    raw_gallery = safe_get("gallery_urls") or safe_get("photos")
    gallery = _safe_json_list(raw_gallery)
    
    # Normalize gallery URLs
    normalized_gallery = []
    for g in gallery:
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            url = g.get("url") if isinstance(g, dict) else str(g)
        except Exception:
            url = None
        if url:
            url_norm = _normalize_cover_url(url)
            if url_norm and url_norm != COVER_PLACEHOLDER:
                normalized_gallery.append(url_norm)
    
    # Normalize cover, fallback to first gallery image
    cover_url = _normalize_cover_url(raw_cover)
    if (not raw_cover or cover_url == COVER_PLACEHOLDER) and normalized_gallery:
        cover_url = normalized_gallery[0]
    
    # Parse publishing fields
    is_published = safe_get("is_published")
    if is_published is None:
        is_published = True  # default for legacy items
    else:
        is_published = bool(is_published)
    
    published_at = safe_get("published_at")
    status = "published" if is_published else "draft"
    
    # Safe price calculation
    price = safe_get("price", 0)
    price_cents = safe_get("price_cents") or (int(price * 100) if price else 0)
    
    # Parse STL extra files (may be JSON string or list)
    raw_stl_extra = safe_get("stl_extra_urls") or safe_get("stl_extra")
    stl_extra = _safe_json_list(raw_stl_extra)
    
    # Get main STL URL
    stl_main = safe_get("stl_main_url") or safe_get("url") or safe_get("file_url")
    
    # ✅ Filter out empty/invalid URLs
    # Remove None, empty strings, whitespace-only URLs from extras
    stl_extra = [u for u in stl_extra if u and str(u).strip()]
    
    # Validate main URL - set to None if empty/whitespace
    if not (stl_main and str(stl_main).strip()):
        stl_main = None
    
    return {
        "id": safe_get("id"),
        "title": safe_get("title"),
        "price": price,
        "tags": safe_get("tags"),
        "cover_url": cover_url,  # ✅ Always normalized, never "no image"
        "gallery_urls": normalized_gallery,
        "stl_main_url": stl_main,  # ✅ Main 3D file URL (None if empty)
        "stl_extra_urls": stl_extra,  # ✅ Additional 3D files (filtered, no empties)
        "rating": safe_get("rating", 0),
        "downloads": safe_get("downloads", 0),
        "url": stl_main,  # Legacy compatibility
        "format": safe_get("format"),
        "user_id": safe_get("user_id"),
        "author_name": safe_get("author_name"),  # ✅ Author display name
        "author_avatar": safe_get("author_avatar"),  # ✅ Author avatar URL
        "created_at": safe_get("created_at"),
        "price_cents": price_cents,
        "is_free": safe_get("is_free") or (price == 0),
        "is_published": is_published,
        "published_at": published_at,
        "status": status,
        "prints_count": safe_get("prints_count", 0),  # ✅ Number of real prints (makes)
        "proof_score": safe_get("proof_score"),  # ✅ Printability score 0-100
    }


# ───────────────────────────── Proof Score Auto-Migration ─────────────────────────────
def _ensure_proof_score_columns():
    """
    Auto-migration: Add proof_score and slice_hints columns if they don't exist.
    Safe, idempotent, works for both PostgreSQL and SQLite.
    """
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        dialect = db.session.get_bind().dialect.name
        
        # Check and add printability_json
        if not _has_column(ITEMS_TBL, "printability_json"):
            db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN printability_json TEXT"))
            db.session.commit()
            current_app.logger.info(f"✅ Added column {ITEMS_TBL}.printability_json")
        
        # Check and add proof_score
        if not _has_column(ITEMS_TBL, "proof_score"):
            db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN proof_score INTEGER"))
            db.session.commit()
            current_app.logger.info(f"✅ Added column {ITEMS_TBL}.proof_score")
        
        # Check and add analyzed_at
        if not _has_column(ITEMS_TBL, "analyzed_at"):
            if dialect == "postgresql":
                db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN analyzed_at TIMESTAMP"))
            else:  # SQLite
                db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN analyzed_at TEXT"))
            db.session.commit()
            current_app.logger.info(f"✅ Added column {ITEMS_TBL}.analyzed_at")
        
        # Check and add slice_hints_json
        if not _has_column(ITEMS_TBL, "slice_hints_json"):
            db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN slice_hints_json TEXT"))
            db.session.commit()
            current_app.logger.info(f"✅ Added column {ITEMS_TBL}.slice_hints_json")
        
        # Check and add slice_hints_at
        if not _has_column(ITEMS_TBL, "slice_hints_at"):
            if dialect == "postgresql":
                db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN slice_hints_at TIMESTAMP"))
            else:  # SQLite
                db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN slice_hints_at TEXT"))
            db.session.commit()
            current_app.logger.info(f"✅ Added column {ITEMS_TBL}.slice_hints_at")
        
        # Clear column cache to force re-check
        global _column_cache
        _column_cache.clear()
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"⚠️ Proof Score migration failed (may already exist): {e}")


_proof_score_migration_done = False

@bp.before_app_request
def _init_proof_score_schema():
    """
    Initialize Proof Score schema on first request.
    Ensures columns exist before any printability endpoint is called.
    """
    global _proof_score_migration_done
    if _proof_score_migration_done:
        return
    
    p = request.path or ""
    if not (p.startswith("/market") or p.startswith("/api/")):
        return
    
    _proof_score_migration_done = True
    
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        _ensure_proof_score_columns()
        current_app.logger.info("✅ Proof Score schema ensured")
    except Exception as e:
        current_app.logger.error(f"❌ Proof Score schema initialization failed: {e}")


# ───────────────────────────── Safe DB migration ─────────────────────────────
_migration_done = False

@bp.before_app_request
def _ensure_publishing_columns():
    """
    Safe migration: add is_published and published_at columns if they don't exist.
    HOTFIX: Never crashes, always falls back gracefully.
    """
    global _migration_done
    if _migration_done:
        return
    
    p = request.path or ""
    if not (p.startswith("/market") or p.startswith("/api/")):
        return
    
    _migration_done = True
    
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        dialect = db.session.get_bind().dialect.name
        
        # Check if columns exist by trying to query them
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            # Column exists, migration already done
            return
        except Exception:
            db.session.rollback()
        
        # Columns don't exist, add them
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            if dialect == "postgresql":
                # PostgreSQL supports IF NOT EXISTS
                db.session.execute(text(f"""
                    ALTER TABLE {ITEMS_TBL} 
                    ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT TRUE
                """))
                db.session.execute(text(f"""
                    ALTER TABLE {ITEMS_TBL} 
                    ADD COLUMN IF NOT EXISTS published_at TIMESTAMP
                """))
            else:
                # SQLite doesn't support IF NOT EXISTS in ALTER TABLE
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN is_published INTEGER DEFAULT 1"))
                except Exception as e:
                    if not _is_missing_column_error(e):
                        current_app.logger.warning(f"is_published column add failed: {e}")
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN published_at TIMESTAMP"))
                except Exception as e:
                    if not _is_missing_column_error(e):
                        current_app.logger.warning(f"published_at column add failed: {e}")
            
            db.session.commit()
            current_app.logger.info("✅ Publishing columns added successfully")
        except Exception as e:
            db.session.rollback()
            current_app.logger.warning(f"⚠️ Migration failed (columns may already exist): {e}")
    except Exception as e:
        # Global catch-all to prevent any migration crash
        current_app.logger.error(f"❌ Migration error (continuing anyway): {e}")

# ───────────────────────────── NEW: категорії в g ─────────────────────────────
_follow_migration_done = False
_makes_migration_done = False
_makes_verified_migration_done = False
_review_image_migration_done = False

@bp.before_app_request
def _ensure_follow_table():
    """
    Safe migration: create user_follows table if it doesn't exist.
    """
    global _follow_migration_done
    if _follow_migration_done:
        return

    p = request.path or ""
    if not (p.startswith("/market") or p.startswith("/api/")):
        return

    _follow_migration_done = True

    try:
        pass
    except Exception as e:
        pass  # auto-fix missing except
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        dialect = db.session.get_bind().dialect.name
        
        # Створюємо таблицю з урахуванням діалекту
        if dialect == "postgresql":
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS user_follows (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    follower_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """))
        else:
            # SQLite
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS user_follows (
                    id INTEGER PRIMARY KEY,
                    follower_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

        # унікальність (SQLite: через index, Postgres: теж ок)
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_user_follows_pair
            ON user_follows (follower_id, author_id)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_user_follows_follower
            ON user_follows (follower_id)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_user_follows_author
            ON user_follows (author_id)
        """))

        db.session.commit()
        current_app.logger.info("✅ user_follows table ensured")
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"⚠️ follow table ensure failed: {e}")


@bp.before_app_request
def _ensure_item_makes_table():
    """
    Safe migration: create item_makes table if it doesn't exist.
    """
    global _makes_migration_done
    if _makes_migration_done:
        return

    p = request.path or ""
    if not (p.startswith("/market") or p.startswith("/api/")):
        return

    _makes_migration_done = True

    try:
        pass
    except Exception as e:
        pass  # auto-fix missing except
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        dialect = db.session.get_bind().dialect.name
        
        # Створюємо таблицю з урахуванням діалекту
        if dialect == "postgresql":
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS item_makes (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    item_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    image_url TEXT NOT NULL,
                    caption TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """))
        else:
            # SQLite
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS item_makes (
                    id INTEGER PRIMARY KEY,
                    item_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    image_url TEXT NOT NULL,
                    caption TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

        # Індекси
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_item_makes_item
            ON item_makes (item_id)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_item_makes_user
            ON item_makes (user_id)
        """))

        db.session.commit()
        current_app.logger.info("✅ item_makes table ensured")
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"⚠️ makes table ensure failed: {e}")


@bp.before_app_request
def _ensure_review_image_column():
    """
    Safe migration: add image_url column to market_reviews if it doesn't exist.
    """
    global _review_image_migration_done
    if _review_image_migration_done:
        return

    p = request.path or ""
    if not (p.startswith("/market") or p.startswith("/api/")):
        return

    _review_image_migration_done = True

    try:
        pass
    except Exception as e:
        pass  # auto-fix missing except
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        dialect = db.session.get_bind().dialect.name
        
        if dialect == "postgresql":
            # PostgreSQL supports IF NOT EXISTS
            db.session.execute(text("""
                ALTER TABLE market_reviews 
                ADD COLUMN IF NOT EXISTS image_url TEXT
            """))
        else:
            # SQLite doesn't support IF NOT EXISTS, need try/except
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                db.session.execute(text("""
                    ALTER TABLE market_reviews 
                    ADD COLUMN image_url TEXT
                """))
            except sa_exc.OperationalError as e:
                # Column already exists
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    db.session.rollback()
                else:
                    raise

        db.session.commit()
        current_app.logger.info("✅ market_reviews.image_url column ensured")
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"⚠️ review image column ensure failed: {e}")


@bp.before_app_request
def _ensure_makes_verified_column():
    """
    Safe migration: add verified column to item_makes if it doesn't exist.
    """
    global _makes_verified_migration_done
    if _makes_verified_migration_done:
        return

    p = request.path or ""
    if not (p.startswith("/market") or p.startswith("/api/")):
        return

    _makes_verified_migration_done = True

    try:
        pass
    except Exception as e:
        pass  # auto-fix missing except
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        dialect = db.session.get_bind().dialect.name
        
        if dialect == "postgresql":
            # PostgreSQL supports IF NOT EXISTS
            db.session.execute(text("""
                ALTER TABLE item_makes 
                ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE
            """))
        else:
            # SQLite doesn't support IF NOT EXISTS, need try/except
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                db.session.execute(text("""
                    ALTER TABLE item_makes 
                    ADD COLUMN verified INTEGER NOT NULL DEFAULT 0
                """))
            except sa_exc.OperationalError as e:
                # Column already exists
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    db.session.rollback()
                else:
                    raise

        db.session.commit()
        current_app.logger.info("✅ item_makes.verified column ensured")
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"⚠️ makes verified column ensure failed: {e}")


@bp.before_app_request
def _inject_market_categories():
    """
    Inject g.market_categories on market pages.
    """
    p = request.path or ""
    if not (p.startswith("/market") or p.startswith("/api/market") or p.startswith("/api/")):
        return
    try:
        if MarketCategory is None:
            g.market_categories = []
            return
        g.market_categories = MarketCategory.query.order_by(MarketCategory.name.asc()).all()
    except Exception:
        g.market_categories = []
# ──────────────────────────────────────────────────────────────────────────────


@bp.get("/market")
def page_market():
    owner = (request.args.get("owner") or "").strip().lower()
    if owner in ("me", "my", "mine"):
        return render_template("market/my-ads.html")
    
    # Pass author_id to template if filtering by author
    author_id = _parse_int(request.args.get("author_id"), 0)
    
    # ❤️ Server-side favorites: load fav_ids for SSR heart states
    current_user_id = _get_uid()
    fav_ids = set()
    if current_user_id:
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            fav_ids = set(
                r[0] for r in db.session.query(MarketFavorite.item_id)
                .filter(MarketFavorite.user_id == current_user_id)
                .all()
            )
        except Exception as e:
            current_app.logger.warning("[page_market] Failed to load favorites: %s", e)
    
    # 📝 Debug log: track uid and favorites count
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        current_app.logger.info("[market_page] uid=%s fav_cnt=%s", current_user_id, len(fav_ids or []))
    except Exception:
        current_app.logger.exception("[market_page] log failed")
    
    return render_template("market/index.html", author_id=author_id or None, fav_ids=fav_ids)


@bp.get("/market/top-prints")
def page_market_top_prints():
    """Top Prints Leaderboard - dedicated page with top models and authors"""
    return render_template("market/top_prints.html")


@bp.get("/market/mine")
def page_market_mine():
    return render_template("market_mine.html")


@bp.get("/market/my-ads")
def page_market_my_ads():
    return render_template("market/my-ads.html")


@bp.get("/market/my")
def page_market_my():
    return render_template("market/my.html")


@bp.get("/market/following")
def page_market_following():
    """Feed from followed authors"""
    # 🔥 CRITICAL FIX: Use session (Flask-Login not initialized)
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return redirect(url_for("auth.login", next=request.path))
    return render_template("market/following.html")


@bp.get("/item/<int:item_id>")
def page_item(item_id: int):
    reviews = []
    it = _fetch_item_with_author(item_id)
    if not it:
        return render_template("item.html", item=None), 404

    # it can be model, Row, mapping, or (bug) an int id
    if isinstance(it, int):
        # fallback: treat it as item_id and fetch item object
        it = MarketItem.query.get_or_404(it)

    # SQLAlchemy Row -> mapping
    if hasattr(it, "_mapping"):
        d = dict(it._mapping)
    elif isinstance(it, dict):
        d = it
    else:
        # SQLAlchemy model -> dict via columns
        d = {c.name: getattr(it, c.name, None) for c in it.__table__.columns}
    d["owner"] = {
        "name": d.get("author_name") or "-",
        "avatar_url": d.get("author_avatar") or "/static/img/user.jpg",
        "bio": d.get("author_bio") or "3D-дизайнер",
    }

    if "price_cents" not in d:
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            price_pln = float(d.get("price") or 0)
            d["price_cents"] = int(round(price_pln * 100))
        except Exception:
            d["price_cents"] = 0
    d["is_free"] = bool(d.get("is_free")) or (int(d.get("price_cents") or 0) == 0)

    d["main_model_url"] = d.get("stl_main_url") or d.get("url")
    d["cover_url"] = _normalize_cover_url(d.get("cover_url") or d.get("cover"))

    # Перевірка чи це власний item
    uid = _parse_int(session.get("user_id"), 0)
    d["is_owner"] = uid and uid == d.get("author_id")

    # Social proof metrics
    d["prints_count"] = 0
    d["reviews_count"] = 0
    d["verified_reviews_count"] = 0
    d["followers_count"] = 0
    
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        # Prints count
        prints = db.session.execute(
            text("SELECT COUNT(*) FROM item_makes WHERE item_id = :item_id"),
            {"item_id": item_id}
        ).scalar()
        d["prints_count"] = int(prints or 0)
    except (sa_exc.ProgrammingError, sa_exc.OperationalError) as e:
        if not _is_missing_table_error(e):
            current_app.logger.error(f"Prints count error: {e}")
    
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        # Reviews count
        reviews_total = db.session.execute(
            text("SELECT COUNT(*) FROM market_reviews WHERE item_id = :item_id"),
            {"item_id": item_id}
        ).scalar()
        d["reviews_count"] = int(reviews_total or 0)
        
        # Verified reviews count (users who have made prints)
        verified = db.session.execute(
            text("""
                SELECT COUNT(DISTINCT r.id)
                FROM market_reviews r
                WHERE r.item_id = :item_id
                AND EXISTS (
                    SELECT 1 FROM item_makes m
                    WHERE m.item_id = r.item_id AND m.user_id = r.user_id
                )
            """),
            {"item_id": item_id}
        ).scalar()
        d["verified_reviews_count"] = int(verified or 0)
    except (sa_exc.ProgrammingError, sa_exc.OperationalError) as e:
        if not _is_missing_table_error(e):
            current_app.logger.error(f"Reviews count error: {e}")
    
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        # Followers count for this item's author
        author_id = d.get("author_id")
        if author_id:
            followers = db.session.execute(
                text("SELECT COUNT(*) FROM user_follows WHERE author_id = :author_id"),
                {"author_id": author_id}
            ).scalar()
            d["followers_count"] = int(followers or 0)
    except (sa_exc.ProgrammingError, sa_exc.OperationalError) as e:
        if not _is_missing_table_error(e):
            current_app.logger.error(f"Followers count error: {e}")

    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        reviews = (
            MarketReview.query.filter_by(item_id=item_id)
            .order_by(MarketReview.created_at.desc())
            .limit(50)
            .all()
        )
    except Exception:
        reviews = []

    d["reviews"] = reviews
    d["ratings_cnt"] = len(reviews)

    # ✅ Prepare STL URLs list for multi-file switcher (max 5)
    stl_urls = []
    if d.get("stl_main_url"):
        stl_urls.append(d["stl_main_url"])
    
    # Add extra STL files from stl_files or stl_extra_urls
    extra_stls = d.get("stl_files") or _safe_json_list(d.get("stl_extra_urls"))
    if extra_stls:
        stl_urls.extend([u for u in extra_stls if u and str(u).strip()])
    
    # Remove duplicates while preserving order, limit to 5
    seen = set()
    stl_urls = [u for u in stl_urls if u and not (u in seen or seen.add(u))][:5]
    
    # ✅ Prepare gallery URLs for thumbnails
    gallery_urls = d.get("gallery_urls") or d.get("photos")
    if not isinstance(gallery_urls, list):
        gallery_urls = _safe_json_list(gallery_urls)
    # guard: DB може повернути NULL/None
    gallery_urls = gallery_urls or []
    gallery_urls = [u for u in gallery_urls if u and str(u).strip()][:10]

    # ✅ DEBUG: Log what we're passing to template
    current_app.logger.warning(
        f"[PAGE_ITEM] id={item_id} "
        f"stl_main={d.get('stl_main_url')[:80] if d.get('stl_main_url') else None}... "
        f"stl_extras_raw={d.get('stl_extra_urls')} "
        f"stl_extras_parsed={extra_stls} "
        f"stl_urls_final={stl_urls} "
        f"gallery={len(gallery_urls)} items"
    )

    return render_template(
        "market/detail.html",
        item=d,
        stl_urls=stl_urls,
        gallery_urls=gallery_urls
    )


@bp.get("/upload")
def page_upload():
    return render_template("upload.html")


@bp.get("/market/upload")
def page_market_upload():
    return render_template("upload.html")


@bp.get("/edit/<int:item_id>")
def page_edit_item(item_id: int):
    """Legacy route - redirect to canonical /market/edit/<id>"""
    return redirect(url_for('market.page_market_edit_item', item_id=item_id))


@bp.get("/market/edit/<int:item_id>")
def page_market_edit_item(item_id: int):
    # 🔥 CRITICAL FIX: Use session (Flask-Login not initialized)
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        abort(401)

    it = _fetch_item_with_author(item_id)
    if not it:
        abort(404)

    if _parse_int(it.get("user_id"), 0) != uid:
        abort(403)

    return render_template("market/edit_model.html", item=it)


# ============================================================
# � COMPAT ENDPOINT - Favorite Toggle (used by market_listeners.js)
# ============================================================

@bp.route("/api/market/favorite", methods=["POST"], strict_slashes=False)
def api_market_favorite_compat():
    """
    ✅ COMPAT: Toggle favorite status for market item
    Called by: market_listeners.js → POST /api/market/favorite
    
    Request JSON: { "item_id": 123, "on": true/false }
    Response: { "ok": true, "on": true/false }
    
    This endpoint ensures market_listeners.js always has a working route
    even if market_api.py blueprint fails to register.
    """
    # Get user ID from session
    uid = _get_uid()
    if not uid:
        current_app.logger.warning("[api_market_favorite] Unauthorized request")
        return jsonify(ok=False, error="auth_required"), 401
    
    # Parse request data
    data = request.get_json(silent=True) or {}
    
    try:
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        item_id = int(data.get("item_id") or 0)
    except (ValueError, TypeError):
        current_app.logger.warning(f"[api_market_favorite] Invalid item_id: {data.get('item_id')}")
        return jsonify(ok=False, error="invalid_item_id"), 400
    
    if item_id <= 0:
        return jsonify(ok=False, error="missing_item_id"), 400
    
    # Get 'on' parameter (default: true for toggle behavior)
    on = data.get("on")
    
    current_app.logger.info(
        f"[api_market_favorite] uid={uid} item_id={item_id} on={on}"
    )
    
    try:
        pass
    except Exception as e:
        pass  # auto-fix missing except
        pass  # auto-fix empty try body
    except Exception as e:
        pass  # auto-fix missing except
        # Check if favorite exists
        fav = MarketFavorite.query.filter_by(user_id=uid, item_id=item_id).first()
        
        if on is True:
            # Ensure favorite exists
            if not fav:
                db.session.add(MarketFavorite(user_id=uid, item_id=item_id, created_at=datetime.utcnow()))
                db.session.commit()
                current_app.logger.info(f"[api_market_favorite] ✅ Added favorite: uid={uid} item={item_id}")
            return jsonify(ok=True, on=True)
        
        elif on is False:
            # Ensure favorite doesn't exist
            if fav:
                db.session.delete(fav)
                db.session.commit()
                current_app.logger.info(f"[api_market_favorite] ❌ Removed favorite: uid={uid} item={item_id}")
            return jsonify(ok=True, on=False)
        
        else:
            # Toggle behavior (on=null/undefined)
            if fav:
                db.session.delete(fav)
                db.session.commit()
                current_app.logger.info(f"[api_market_favorite] 🔄 Toggled OFF: uid={uid} item={item_id}")
                return jsonify(ok=True, on=False)
            else:
                db.session.add(MarketFavorite(user_id=uid, item_id=item_id, created_at=datetime.utcnow()))
                db.session.commit()
                current_app.logger.info(f"[api_market_favorite] 🔄 Toggled ON: uid={uid} item={item_id}")
                return jsonify(ok=True, on=True)
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"[api_market_favorite] Error: {e}")
        return jsonify(ok=False, error="database_error"), 500


# ============================================================
# �🔍 DEBUG ENDPOINT - Favorites Schema Diagnosis
# ============================================================

@bp.get("/api/_debug/favorites-schema")
def debug_favorites_schema():
    """
    Діагностика: які таблиці *fav* існують в БД та їх колонки.
    Відповідь: { "tables": [...], "columns": { "table_name": [...] } }
    """
    from models import db
    
    # 1) Знайти всі таблиці з 'fav' в назві
    tables_result = db.session.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name ILIKE '%fav%'
        ORDER BY table_name;
    """)).fetchall()
    
    tables_list = [row[0] for row in tables_result]
    
    # 2) Для кожної таблиці отримати колонки та типи
    columns_dict = {}
    for table_name in tables_list:
        cols_result = db.session.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :tname
            ORDER BY ordinal_position;
        """), {"tname": table_name}).fetchall()
        
        columns_dict[table_name] = [
            {"column": col, "type": typ} for col, typ in cols_result
        ]
    
    return jsonify({
        "ok": True,
        "tables": tables_list,
        "columns": columns_dict
    })


@bp.get("/api/items")
def api_items():
    from models import MarketItem
    from sqlalchemy import desc
    try:
        page = max(1, int(request.args.get("page", 1) or 1))
        per_page = min(48, max(1, int(request.args.get("per_page", 24) or 24)))
        sort = (request.args.get("sort") or "new").lower()
        q = (request.args.get("q") or "").strip()

        query = MarketItem.query

        # базовий пошук (мінімально безпечно)
        if q:
            # якщо в моделі є title/tags — буде працювати; якщо ні — просто ігноруємо
            if hasattr(MarketItem, "title"):
                query = query.filter(MarketItem.title.ilike(f"%{q}%"))
            elif hasattr(MarketItem, "name"):
                query = query.filter(MarketItem.name.ilike(f"%{q}%"))

        # сортування
        if sort in ("new", "latest"):
            if hasattr(MarketItem, "created_at"):
                query = query.order_by(desc(MarketItem.created_at))
            else:
                query = query.order_by(desc(MarketItem.id))
        else:
            query = query.order_by(desc(MarketItem.id))

        total = query.count()
        items = query.offset((page - 1) * per_page).limit(per_page).all()

        # серіалізація: віддаємо мінімум полів, які точно не впадуть
        out = []
        for it in items:
            out.append({
                "id": it.id,
                "title": getattr(it, "title", None) or getattr(it, "name", None) or f"Item {it.id}",
                "price": getattr(it, "price", 0) or 0,
                "cover_url": getattr(it, "cover_url", "") or "",
            })

        pages = (total + per_page - 1) // per_page if per_page else 1
        return jsonify({"ok": True, "items": out, "page": page, "pages": pages, "total": total}), 200

    except Exception as e:
        current_app.logger.exception("[api_items] failed")
        # ⚠️ навіть при помилці ми ПОВЕРТАЄМО jsonify → 500 буде з читабельним текстом
        return jsonify({"ok": False, "error": str(e)}), 500
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json) != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
        # Proof Score filter
        if min_proof_score > 0:
            where.append("i.proof_score >= :min_proof_score")
            params["min_proof_score"] = min_proof_score
        
        # Auto presets filter (has slice hints)
        if auto_presets:
            where.append(
                "i.slice_hints_json IS NOT NULL "
                "AND i.slice_hints_json != '' "
                "AND i.slice_hints_json != '{}' "
                "AND LOWER(i.slice_hints_json) != 'null'"
            )
        
        # ✅ Filter only published items in public market
        try:
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(i.is_published = :pub OR i.is_published IS NULL)")
            params["pub"] = True
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # 🔍 DEBUG: Log sort value before ORDER BY
        current_app.logger.info(f"[api_items] 🔍 sort='{sort}', mode='{mode}'")

        # Top Prints mode: ranking by quality
        if mode == "top":
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Check if proof_score column exists
                db.session.execute(text(f"SELECT proof_score FROM {ITEMS_TBL} LIMIT 1")).fetchone()
                
                # Optional: only show items with proof_score
                if "i.proof_score IS NOT NULL" not in " ".join(where):
                    if where:
                        where.append("i.proof_score IS NOT NULL")
                    else:
                        where = ["i.proof_score IS NOT NULL"]
                    where_sql = "WHERE " + " AND ".join(where)
                
                # Ranking formula: proof_score + bonus for slice_hints
                # Using CASE to add +15 if slice_hints is valid
                if dialect == "postgresql":
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                else:  # SQLite
                    ranking_expr = """(
                        COALESCE(i.proof_score, 0) + 
                        CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                            AND i.slice_hints_json != '' 
                            AND i.slice_hints_json != '{}' 
                            AND LOWER(i.slice_hints_json) != 'null' 
                            THEN 15 
                            ELSE 0 
                        END
                    )"""
                
                order_sql = f"ORDER BY {ranking_expr} DESC, i.created_at DESC"
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Top mode ranking failed (proof_score missing?): {e} | "
                    f"Falling back to default ordering"
                )
                # Fallback: columns don't exist, use default ordering
                order_sql = "ORDER BY i.created_at DESC, i.id DESC"
        elif sort == "price_asc":
            order_sql = "ORDER BY i.price ASC, i.created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY i.price DESC, i.created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY i.downloads DESC, i.created_at DESC"
        elif sort == "prints":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_7d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        elif sort == "prints_30d":
            order_sql = "ORDER BY prints_count DESC, i.created_at DESC"
        else:
            order_sql = "ORDER BY i.created_at DESC, i.id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            pass
        except Exception as e:
            pass  # auto-fix missing except
            pass  # auto-fix empty try body
        except Exception as e:
            pass  # auto-fix missing except
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
                pass  # auto-fix empty try body
            except Exception as e:
                pass  # auto-fix missing except
                # Determine date filter for trending prints
                date_filter = ""
                if sort == "prints_7d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
                elif sort == "prints_30d":
                    if dialect == "postgresql":
                        date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
                    else:  # SQLite
                        date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
                
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # Execute main SELECT (saved_only already returned above)
                try:
                    pass  # auto-fix empty try body
                except Exception as e:
                    pass  # auto-fix missing except
                    rows = db.session.execute(
                        text(sql_with_publish),
                        {**params, "limit": per_page, "offset": offset},
                    ).fetchall()
                except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                    # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                    db.session.rollback()
                    rows = []
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ Trending prints date filter failed: {e} | "
                    f"Falling back to query without date filter"
                )
                
                # Fallback: query without date filter
                sql_with_publish = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           i.is_published, i.published_at,
                           COALESCE(pm.prints_count, 0) AS prints_count,
                           i.proof_score,
                           i.slice_hints_json,
                           u.name AS author_name
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_with_publish),
                    {**params, "limit": per_page, "offset": offset},
                ).fetchall()
            
            # Build items with is_favorite
            items = []
            for r in rows:
                item = _row_to_dict(r)
                # ✅ All items in saved_only are favorites by definition
                item['is_favorite'] = True
                item['is_fav'] = 1  # Legacy compatibility (integer for frontend)
                item['has_slice_hints'] = False  # Simplified for saved_only
                items.append(item)
            
            # COUNT query for saved items
            count_sql_saved = f"""
                SELECT COUNT(*) 
                FROM {ITEMS_TBL} i
                {where_sql_saved}
            """
            count_stmt_saved = text(count_sql_saved).bindparams(bindparam("fav_ids", expanding=True))
            total = db.session.execute(count_stmt_saved, params_saved).scalar() or 0
            
            # Serialize and return (NO fallback possible)
            items = [_item_to_dict(it) for it in items]
            
            current_app.logger.warning("[api_items] 🔥 SAVED_ONLY return: items=%d total=%d", len(items), total)
            return jsonify({
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            })
        
        # Author filter: resolve username -> user_id
        author_param = request.args.get("author", "").strip()
        author_user_id = None
        
        if author_param:
            # Validate username with allowlist regex
            import re
            if re.match(r'^[A-Za-z0-9_-]{1,50}$', author_param):
                # Lookup user_id by username
                user_row = db.session.execute(
                    text(f"SELECT id FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
                    {"name": author_param}
                ).fetchone()
                
                if user_row:
                    author_user_id = user_row.id
                else:
                    # Author not found - return empty result (don't crash)
                    return jsonify({
                        "ok": True,
                        "items": [],
                        "page": page,
                        "per_page": per_page,
                        "pages": 0,
                        "total": 0
                    })
            else:
                # Invalid username format - return empty result
                return jsonify({
                    "ok": True,
                    "items": [],
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                    "total": 0
                })
        
        # Legacy author_id param (for backwards compatibility)
        author_id = _parse_int(request.args.get("author_id"), 0)
        if author_id > 0 and not author_user_id:
            author_user_id = author_id
        
        # Proof Score / Slice Hints filters
        auto_presets = request.args.get("auto_presets") == "1"
        min_proof_score = _parse_int(request.args.get("min_proof_score"), 0)

        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
            tags_expr = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"
        else:
            title_expr = "LOWER(COALESCE(title, ''))"
            tags_expr = "LOWER(COALESCE(tags,  ''))"
            cover_expr = "COALESCE(cover_url, '')"
            url_expr = "stl_main_url"

        where, params = [], {}
        
        # ❤️ Always add current_user_id to params (для можливих SQL що його використовують)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or 0)
        
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("i.price = 0")
        elif free == "paid":
            where.append("i.price > 0")
        
        # Author filter
        if author_user_id is not None:
            where.append("i.user_id = :author_id")
            params["author_id"] = author_user_id
        
        # NOTE: saved_only handled in dedicated path above (early return)
        # This section only executes for non-saved queries
        
       
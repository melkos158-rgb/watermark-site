import os
import math
import json
import shutil
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List

from flask import (
    Blueprint,
    render_template,
    jsonify,
    request,
    session,
    current_app,
    send_from_directory,
    abort,
    redirect,
    g,
    url_for,
    make_response,
)
from sqlalchemy import text
from sqlalchemy import exc as sa_exc
from werkzeug.utils import secure_filename

# ✅ Cloudinary (хмарне зберігання)
# Працює, якщо в ENV є CLOUDINARY_URL=cloudinary://<key>:<secret>@<cloud_name>
try:
    import cloudinary
    import cloudinary.uploader

    _CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
    # cloudinary сам читає CLOUDINARY_URL з env, конфіг не обов'язковий
    # але залишаємо, якщо в тебе так задумано:
    if _CLOUDINARY_URL:
        try:
            cloudinary.config(cloudinary_url=_CLOUDINARY_URL)
        except Exception:
            pass
    _CLOUDINARY_READY = bool(_CLOUDINARY_URL)
except Exception:
    _CLOUDINARY_READY = False

# ✅ беремо db та модель з models.py
from models import db, MarketItem, MarketFavorite, MarketReview, UserFollow
# якщо User у тебе лишається в db.py — імпортуємо тільки його звідти
from db import User

# ✅ категорії з нового market-модуля
try:
    from models_market import MarketCategory  # для g.market_categories
except Exception:
    MarketCategory = None  # fallback, якщо поки не підключено

bp = Blueprint("market", __name__)

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
    """
    Convert /media/... or /static/market_uploads/... URL to absolute filesystem path.
    Returns None if file is Cloudinary (HTTPS) or doesn't exist locally.
    """
    if not url:
        return None
    
    # Skip Cloudinary URLs (can't analyze remote files in MVP)
    if url.startswith("http://") or url.startswith("https://"):
        return None
    
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
    Get current user ID with Flask-Login fallback to session.
    Returns None if not authenticated.
    """
    # Try Flask-Login first (if initialized)
    try:
        from flask_login import current_user
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            return current_user.id
    except (ImportError, AttributeError, RuntimeError):
        pass
    
    # Fallback to session
    return session.get("user_id")


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
            folder = f"proofly/market/{subdir}".replace("\\", "/")

            # важливо: якщо stream вже читався — повернемось на 0
            try:
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
                current_app.logger.warning(
                    f"Cloudinary upload failed, fallback to local: {type(_e).__name__}: {_e}"
                )
            except Exception:
                pass

    # Preferred root from config/env
    root = _uploads_root()
    try:
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
    
    return {
        "id": safe_get("id"),
        "title": safe_get("title"),
        "price": price,
        "tags": safe_get("tags"),
        "cover_url": cover_url,  # ✅ Always normalized, never "no image"
        "gallery_urls": normalized_gallery,
        "rating": safe_get("rating", 0),
        "downloads": safe_get("downloads", 0),
        "url": safe_get("url") or safe_get("stl_main_url"),
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
        dialect = db.session.get_bind().dialect.name
        
        # Check if columns exist by trying to query them
        try:
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            # Column exists, migration already done
            return
        except Exception:
            db.session.rollback()
        
        # Columns don't exist, add them
        try:
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
                    db.session.execute(text(f"ALTER TABLE {ITEMS_TBL} ADD COLUMN is_published INTEGER DEFAULT 1"))
                except Exception as e:
                    if not _is_missing_column_error(e):
                        current_app.logger.warning(f"is_published column add failed: {e}")
                try:
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
    cats = []
    if MarketCategory is not None:
        try:
            cats = MarketCategory.query.order_by(MarketCategory.name.asc()).all()
        except Exception:
            cats = []
    g.market_categories = cats
# ──────────────────────────────────────────────────────────────────────────────


@bp.get("/market")
def page_market():
    owner = (request.args.get("owner") or "").strip().lower()
    if owner in ("me", "my", "mine"):
        return render_template("market/my-ads.html")
    
    # Pass author_id to template if filtering by author
    author_id = _parse_int(request.args.get("author_id"), 0)
    return render_template("market/index.html", author_id=author_id or None)


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
    it = _fetch_item_with_author(item_id)
    if not it:
        return render_template("item.html", item=None), 404

    d = dict(it)
    d["owner"] = {
        "name": d.get("author_name") or "-",
        "avatar_url": d.get("author_avatar") or "/static/img/user.jpg",
        "bio": d.get("author_bio") or "3D-дизайнер",
    }

    if "price_cents" not in d:
        try:
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

    return render_template("market/detail.html", item=d)


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
# 🔍 DEBUG ENDPOINT - Favorites Schema Diagnosis
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
    try:
        raw_q = request.args.get("q") or ""
        q = raw_q.strip().lower()

        free = _normalize_free(request.args.get("free"))
        sort = _normalize_sort(request.args.get("sort"))
        mode = request.args.get("mode") or ""  # top / empty
        page = max(1, _parse_int(request.args.get("page"), 1))
        per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))
        
        # 🔍 DEBUG: Log normalized sort immediately
        current_app.logger.info(
            f"[api_items] 🔍 PARAMS: sort='{sort}' (raw='{request.args.get('sort')}'), "
            f"mode='{mode}', page={page}, per_page={per_page}"
        )
        
        # ❤️ Saved filter (Instagram-style favorites)
        saved_only = request.args.get("saved") == "1"
        
        # 🔥 CRITICAL FIX: Use helper for consistent user_id retrieval
        current_user_id = _get_uid()
        is_authenticated = current_user_id is not None
        
        # 🔍 DEBUG: Log params for saved filter debugging
        current_app.logger.info(
            "[api_items] uid=%s saved=%s args=%s",
            current_user_id, saved_only, dict(request.args)
        )
        
        # If saved filter is active, check if user has any favorites
        if saved_only and current_user_id:
            fav_cnt = db.session.execute(
                text(f"SELECT COUNT(*) FROM {FAVORITES_TBL} WHERE user_id = :u"),
                {"u": current_user_id}
            ).scalar()
            current_app.logger.info(
                "[api_items] fav_cnt=%s for uid=%s",
                fav_cnt, current_user_id
            )
        
        # If saved_only=1 without auth, return empty
        if saved_only and not is_authenticated:
            return jsonify({
                "ok": True,
                "items": [],
                "page": page,
                "per_page": per_page,
                "pages": 0,
                "total": 0
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
        
        # ❤️ Always add current_user_id for is_favorite JOIN (even if not saved filter)
        # 🔍 DEBUG: Log current_user state
        current_app.logger.info(
            f"[api_items] 🔍 is_authenticated={is_authenticated}, "
            f"current_user_id={current_user_id}, saved_only={saved_only}"
        )
        params["current_user_id"] = int(current_user_id or -1)
        
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
        
        # ❤️ Saved filter (only show user's favorites)
        # 🔥 FIX: Check current_user_id is not None (0 is valid user_id in some DBs)
        if saved_only and current_user_id is not None:
            # Must have a favorite record (INNER JOIN logic via WHERE)
            where.append("mf.item_id IS NOT NULL")
        
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
            # Build SQL with is_published columns - ALL inside try
            # Try with item_makes LEFT JOIN first
            try:
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
                           u.name AS author_name,
                           CASE WHEN mf.item_id IS NOT NULL THEN 1 ELSE 0 END AS is_fav
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN (
                        SELECT item_id, COUNT(*) AS prints_count
                        FROM item_makes m
                        {date_filter}
                        GROUP BY item_id
                    ) pm ON pm.item_id = i.id
                    LEFT JOIN {FAVORITES_TBL} mf ON mf.item_id = i.id AND mf.user_id = :current_user_id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                # 🔍 DEBUG: Log SQL execution
                current_app.logger.info(
                    f"[api_items] 🔍 Executing SQL with order_sql='{order_sql[:100]}...' | "
                    f"params={list(params.keys())}"
                )
                rows = db.session.execute(text(sql_with_publish), {**params, "limit": per_page, "offset": offset}).fetchall()
            except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
                # ✅ Fallback: item_makes table doesn't exist (old schema / pre-migration)
                db.session.rollback()
                current_app.logger.warning(
                    f"[api_items] ⚠️ item_makes JOIN failed (table missing?): {e} | "
                    f"Falling back to query without prints_count"
                )
                if _is_missing_table_error(e):
                    sql_with_publish = f"""
                        SELECT i.id, i.title, i.price, i.tags,
                               COALESCE(i.cover_url, '') AS cover,
                               COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                               COALESCE(i.rating, 0) AS rating,
                               COALESCE(i.downloads, 0) AS downloads,
                               {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                               i.format, i.user_id, i.created_at,
                               i.is_published, i.published_at,
                               0 AS prints_count,
                               i.proof_score,
                               i.slice_hints_json,
                               u.name AS author_name,
                               CASE WHEN mf.item_id IS NOT NULL THEN 1 ELSE 0 END AS is_fav
                        FROM {ITEMS_TBL} i
                        LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                        LEFT JOIN {FAVORITES_TBL} mf ON mf.item_id = i.id AND mf.user_id = :current_user_id
                        {where_sql}
                        {order_sql}
                        LIMIT :limit OFFSET :offset
                    """
                    rows = db.session.execute(text(sql_with_publish), {**params, "limit": per_page, "offset": offset}).fetchall()
                else:
                    # Re-raise if it's not a missing table error
                    raise
            
            # Add has_slice_hints derived field + is_fav alias
            items = []
            for r in rows:
                item = _row_to_dict(r)
                slice_hints = item.get('slice_hints_json')
                # Check if slice_hints is valid: not None, not empty, not "null" string, not "{}"
                item['has_slice_hints'] = bool(
                    slice_hints 
                    and isinstance(slice_hints, str) 
                    and slice_hints.strip() 
                    and slice_hints.strip().lower() not in ('null', '{}', '')
                )
                items.append(item)
            
            # COUNT query - ALWAYS use JOIN for consistency, use DISTINCT to avoid duplicates
            count_sql = f"""
                SELECT COUNT(DISTINCT i.id) 
                FROM {ITEMS_TBL} i
                LEFT JOIN {FAVORITES_TBL} mf ON mf.item_id = i.id AND mf.user_id = :current_user_id
                {where_sql}
            """
            total = db.session.execute(text(count_sql), params).scalar() or 0
            
        except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
            # 🔄 FALLBACK: Column doesn't exist yet
            db.session.rollback()
            current_app.logger.warning(
                f"[api_items] ⚠️ is_published/proof_score column missing: {e} | "
                f"Falling back to legacy query"
            )
            if _is_missing_column_error(e):
                
                # Rebuild query WITHOUT is_published columns but WITH author_name + is_favorite
                sql_fallback = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr.replace('stl_main_url', 'i.stl_main_url')} AS url,
                           i.format, i.user_id, i.created_at,
                           0 AS prints_count,
                           NULL AS proof_score,
                           NULL AS slice_hints_json,
                           u.name AS author_name,
                           CASE WHEN mf.item_id IS NOT NULL THEN 1 ELSE 0 END AS is_fav
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    LEFT JOIN {FAVORITES_TBL} mf ON mf.item_id = i.id AND mf.user_id = :current_user_id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                
                try:
                    rows = db.session.execute(text(sql_fallback), {**params, "limit": per_page, "offset": offset}).fetchall()
                    items = []
                    for r in rows:
                        item = _row_to_dict(r)
                        item['has_slice_hints'] = False  # Fallback: columns don't exist
                        items.append(item)
                    
                    # COUNT query - ALWAYS use JOIN for consistency, use DISTINCT to avoid duplicates
                    count_sql = f"""
                        SELECT COUNT(DISTINCT i.id) 
                        FROM {ITEMS_TBL} i
                        LEFT JOIN {FAVORITES_TBL} mf ON mf.item_id = i.id AND mf.user_id = :current_user_id
                        {where_sql}
                    """
                    total = db.session.execute(text(count_sql), params).scalar() or 0
                except sa_exc.ProgrammingError:
                    # Last resort: legacy schema with zip_url instead of stl_main_url
                    db.session.rollback()
                    sql_legacy = f"""
                        SELECT i.id, i.title, i.price, i.tags,
                               COALESCE(i.cover_url, '') AS cover,
                               COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                               COALESCE(i.zip_url,'') AS url,
                               i.user_id, i.created_at,
                               0 AS prints_count,
                               u.name AS author_name,
                               CASE WHEN mf.item_id IS NOT NULL THEN 1 ELSE 0 END AS is_fav
                        FROM {ITEMS_TBL} i
                        LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                        LEFT JOIN {FAVORITES_TBL} mf ON mf.item_id = i.id AND mf.user_id = :current_user_id
                        {where_sql}
                        {order_sql}
                        LIMIT :limit OFFSET :offset
                    """
                    rows = db.session.execute(text(sql_legacy), {**params, "limit": per_page, "offset": offset}).fetchall()
                    items = []
                    for r in rows:
                        d = _row_to_dict(r)
                        d.setdefault("rating", 0)
                        d.setdefault("downloads", 0)
                        d.setdefault("proof_score", None)
                        d["has_slice_hints"] = False
                        items.append(d)
                    
                    # COUNT query - ALWAYS use JOIN for consistency, use DISTINCT to avoid duplicates
                    count_sql = f"""
                        SELECT COUNT(DISTINCT i.id) 
                        FROM {ITEMS_TBL} i
                        LEFT JOIN {FAVORITES_TBL} mf ON mf.item_id = i.id AND mf.user_id = :current_user_id
                        {where_sql}
                    """
                    total = db.session.execute(text(count_sql), params).scalar() or 0
            else:
                # Other error - re-raise
                raise

        # ✅ Use universal serializer for consistent cover_url normalization
        items = [_item_to_dict(it) for it in items]

        return jsonify(
            {
                "ok": True,
                "items": items,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "total": total,
            }
        )

    except Exception as e:
        # 🔥 CRITICAL: Return HTTP 500 to expose errors (not hide as "0 items")
        db.session.rollback()  # Clean up aborted transaction
        
        # Safe check for is_authenticated without current_user
        user_id = session.get("user_id")
        current_app.logger.exception(
            "🔥 api_items FAILED: %s | user_id=%s | params=%s",
            e,
            user_id,
            request.args.to_dict()
        )
        
        # Return HTTP 500 with error details for debugging
        return jsonify({
            "ok": False,
            "error": "server_error",
            "message": "Failed to load items. Check server logs.",
            "details": str(e) if current_app.debug else None
        }), 500


@bp.get("/api/market/items")
def api_items_compat():
    return api_items()


@bp.get("/api/my/items")
def api_my_items():
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"error": "unauthorized"}), 401

    page = max(1, _parse_int(request.args.get("page"), 1))
    per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))
    offset = (page - 1) * per_page

    where_clause = "WHERE (user_id = :uid OR user_id IS NULL OR user_id = 0)"

    # ⚠️ HOTFIX: Try query with is_published - ALL inside try
    try:
        sql_with_publish = f"""
            SELECT id, title, price, tags,
                   COALESCE(cover_url, '') AS cover,
                   COALESCE(gallery_urls, '[]') AS gallery_urls,
                   COALESCE(rating, 0) AS rating,
                   COALESCE(downloads, 0) AS downloads,
                   stl_main_url AS url,
                   format, user_id, created_at,
                   is_published, published_at
            FROM {ITEMS_TBL}
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
        """
        
        rows = db.session.execute(text(sql_with_publish), {"uid": uid, "limit": per_page, "offset": offset}).fetchall()
        items = [_row_to_dict(r) for r in rows]
        total = db.session.execute(text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_clause}"), {"uid": uid}).scalar() or 0
        
    except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
        # 🔄 FALLBACK: Column doesn't exist yet
        if _is_missing_column_error(e):
            db.session.rollback()
            
            # Rebuild query WITHOUT is_published columns
            sql_fallback = f"""
                SELECT id, title, price, tags,
                       COALESCE(cover_url, '') AS cover,
                       COALESCE(gallery_urls, '[]') AS gallery_urls,
                       COALESCE(rating, 0) AS rating,
                       COALESCE(downloads, 0) AS downloads,
                       stl_main_url AS url,
                       format, user_id, created_at
                FROM {ITEMS_TBL}
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
            """
            
            try:
                rows = db.session.execute(text(sql_fallback), {"uid": uid, "limit": per_page, "offset": offset}).fetchall()
                items = [_row_to_dict(r) for r in rows]
                total = db.session.execute(text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_clause}"), {"uid": uid}).scalar() or 0
            except sa_exc.ProgrammingError:
                # Last resort: legacy schema
                db.session.rollback()
                sql_legacy = f"""
                    SELECT id, title, price, tags,
                           COALESCE(cover_url, '') AS cover,
                           COALESCE(gallery_urls, '[]') AS gallery_urls,
                           COALESCE(zip_url,'') AS url,
                           user_id, created_at
                    FROM {ITEMS_TBL}
                    {where_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(text(sql_legacy), {"uid": uid, "limit": per_page, "offset": offset}).fetchall()
                items = []
                for r in rows:
                    d = _row_to_dict(r)
                    d.setdefault("rating", 0)
                    d.setdefault("downloads", 0)
                    items.append(d)
                total = db.session.execute(text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_clause}"), {"uid": uid}).scalar() or 0
        else:
            # Other error - re-raise
            raise

    if not total:
        return api_items()

    # ✅ Use universal serializer for consistent cover_url normalization
    items = [_item_to_dict(it) for it in items]

    return jsonify(
        {
            "items": items,
            "page": page,
            "per_page": per_page,
            "pages": math.ceil(total / per_page) if per_page else 1,
            "total": total,
        }
    )


@bp.get("/api/market/my-items")
def api_my_items_compat():
    return api_my_items()


@bp.get("/api/market/my")
def api_my_items_my():
    return api_my_items()


@bp.get("/api/item/<int:item_id>")
def api_item(item_id: int):
    it = _fetch_item_with_author(item_id)
    if not it:
        return jsonify({"error": "not_found"}), 404
    return jsonify(it)


@bp.get("/api/item/related")
@bp.get("/api/items/related")
@bp.get("/api/market/related")
@bp.get("/api/market/items/related")
def api_related_items():
    """Return related/recommended items based on item_id, tags, or category"""
    item_id = request.args.get("item_id")
    limit = min(12, max(3, _parse_int(request.args.get("limit"), 6)))
    
    # If no item_id provided, return random popular items
    if not item_id:
        try:
            sql = f"""
                SELECT id, title, price, tags,
                       COALESCE(cover_url, '') AS cover,
                       COALESCE(rating, 0) AS rating,
                       COALESCE(downloads, 0) AS downloads
                FROM {ITEMS_TBL}
                ORDER BY downloads DESC, rating DESC
                LIMIT :limit
            """
            rows = db.session.execute(text(sql), {"limit": limit}).fetchall()
            items = [_row_to_dict(r) for r in rows]
            for it in items:
                it["cover"] = _normalize_cover_url(it.get("cover"))
                it["cover_url"] = it["cover"]
            return jsonify({"items": items})
        except Exception:
            return jsonify({"items": []})
    
    # Get the source item's tags and category
    try:
        source = db.session.execute(
            text(f"SELECT tags, category FROM {ITEMS_TBL} WHERE id = :id"),
            {"id": item_id}
        ).first()
        
        if not source:
            return jsonify({"items": []})
        
        tags_str = source[0] or ""
        category = source[1] or ""
        
        # Build query for similar items (same tags or category, exclude source item)
        where_clauses = ["id != :item_id"]
        params = {"item_id": item_id, "limit": limit}
        
        if category:
            where_clauses.append("category = :category")
            params["category"] = category
        elif tags_str:
            # Simple tag matching - items with any common tags
            tags_list = [t.strip() for t in tags_str.split(",") if t.strip()]
            if tags_list:
                # Use first few tags for matching
                tag_conditions = []
                for i, tag in enumerate(tags_list[:3]):
                    tag_param = f"tag{i}"
                    tag_conditions.append(f"tags LIKE :{tag_param}")
                    params[tag_param] = f"%{tag}%"
                if tag_conditions:
                    where_clauses.append(f"({' OR '.join(tag_conditions)})")
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        sql = f"""
            SELECT id, title, price, tags,
                   COALESCE(cover_url, '') AS cover,
                   COALESCE(rating, 0) AS rating,
                   COALESCE(downloads, 0) AS downloads
            FROM {ITEMS_TBL}
            WHERE {where_sql}
            ORDER BY rating DESC, downloads DESC
            LIMIT :limit
        """
        
        rows = db.session.execute(text(sql), params).fetchall()
        items = [_row_to_dict(r) for r in rows]
        
        # Normalize cover URLs
        for it in items:
            it["cover"] = _normalize_cover_url(it.get("cover"))
            it["cover_url"] = it["cover"]
        
        return jsonify({"items": items})
        
    except Exception as e:
        current_app.logger.error(f"Related items error: {e}")
        return jsonify({"items": []})



@bp.post("/api/item/<int:item_id>/download")
def api_item_download(item_id: int):
    dialect = db.session.get_bind().dialect.name
    try:
        if dialect == "postgresql":
            upd = db.session.execute(
                text(f"""UPDATE {ITEMS_TBL}
                         SET downloads = COALESCE(downloads,0) + 1,
                             updated_at = NOW()
                         WHERE id = :id"""),
                {"id": item_id}
            )
        else:
            upd = db.session.execute(
                text(f"""UPDATE {ITEMS_TBL}
                         SET downloads = COALESCE(downloads,0) + 1,
                             updated_at = CURRENT_TIMESTAMP
                         WHERE id = :id"""),
                {"id": item_id}
            )
        db.session.commit()
        if upd.rowcount == 0:
            return jsonify({"ok": False, "error": "not_found"}), 404
    except sa_exc.ProgrammingError:
        db.session.rollback()
        try:
            db.session.execute(
                text(
                    f"UPDATE {ITEMS_TBL} SET updated_at = "
                    f"{'NOW()' if dialect == 'postgresql' else 'CURRENT_TIMESTAMP'} "
                    "WHERE id = :id"
                ),
                {"id": item_id}
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
    return jsonify({"ok": True})


# ───────────────────────────── Follow API ─────────────────────────────
@bp.get("/api/user/<int:user_id>/mini")
def api_get_user_mini(user_id: int):
    """Get basic user info for author profile header"""
    try:
        sql = f"""
            SELECT id, name, 
                   COALESCE(avatar_url, '/static/img/user.jpg') AS avatar_url
            FROM {USERS_TBL}
            WHERE id = :user_id
            LIMIT 1
        """
        
        row = db.session.execute(text(sql), {"user_id": user_id}).fetchone()
        
        if not row:
            return jsonify({"ok": False, "error": "user_not_found"}), 404
        
        user_data = _row_to_dict(row)
        
        # Get follower count (how many people follow this author)
        try:
            follower_count = db.session.execute(
                text("SELECT COUNT(*) FROM user_follows WHERE author_id = :uid"),
                {"uid": user_id}
            ).scalar() or 0
            
            # Debug logging
            if current_app.debug:
                current_app.logger.info(f"GET /api/user/{user_id}/mini: followers_count = {follower_count}")
        except Exception as e:
            current_app.logger.warning(f"Failed to get follower count for user {user_id}: {e}")
            follower_count = 0
        
        # Get items count
        try:
            items_count = db.session.execute(
                text(f"SELECT COUNT(*) FROM {ITEMS_TBL} WHERE user_id = :uid"),
                {"uid": user_id}
            ).scalar() or 0
        except Exception:
            items_count = 0
        
        user_data["followers_count"] = follower_count
        user_data["items_count"] = items_count
        
        resp = jsonify({"ok": True, "user": user_data})
        resp.headers["Cache-Control"] = "no-store"
        return resp
        
    except Exception as e:
        current_app.logger.error(f"Get user mini error: {e}")
        return jsonify({"ok": False, "error": "server"}), 500


@bp.get("/api/user/follows")
def api_get_user_follows():
    """Get list of authors current user follows"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        resp = jsonify({"ok": True, "follows": []})
        resp.headers["Cache-Control"] = "no-store"
        return resp
    
    try:
        rows = db.session.execute(
            text("SELECT author_id FROM user_follows WHERE follower_id = :uid"),
            {"uid": uid}
        ).fetchall()
        
        # Return clean list of author IDs (as objects for consistency)
        follows = [{"followed_id": int(r.author_id)} for r in rows]
        
        # Debug logging
        if current_app.debug:
            current_app.logger.info(f"GET /api/user/follows for user {uid}: {follows}")
        
        resp = jsonify({"ok": True, "follows": follows})
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except (sa_exc.ProgrammingError, sa_exc.OperationalError) as e:
        if _is_missing_table_error(e):
            # Table doesn't exist on old schema - return empty list
            return jsonify({"ok": True, "follows": []})
        current_app.logger.error(f"Get follows error: {e}")
        return jsonify({"ok": False, "error": "server"}), 500
    except Exception as e:
        current_app.logger.error(f"Get follows error: {e}")
        return jsonify({"ok": False, "error": "server"}), 500


@bp.get("/api/user/<int:user_id>/followers")
def api_get_user_followers(user_id: int):
    """Get list of users who follow this user"""
    try:
        # Get followers (people who follow this user)
        rows = db.session.execute(
            text(f"""
                SELECT u.id, u.name, COALESCE(u.avatar_url, '/static/img/user.jpg') as avatar_url
                FROM {USERS_TBL} u
                INNER JOIN user_follows uf ON uf.follower_id = u.id
                WHERE uf.author_id = :uid
                ORDER BY uf.created_at DESC
                LIMIT 50
            """),
            {"uid": user_id}
        ).fetchall()
        
        users = [{"id": r.id, "name": r.name, "avatar_url": r.avatar_url} for r in rows]
        
        resp = jsonify({"ok": True, "users": users})
        resp.headers["Cache-Control"] = "no-store"
        return resp
        
    except Exception as e:
        current_app.logger.error(f"Get followers error: {e}")
        return jsonify({"ok": False, "error": "server"}), 500


@bp.get("/api/creator/<username>/stats")
def api_get_creator_stats(username: str):
    """Get aggregated creator reputation metrics"""
    try:
        # Find user by username
        user = db.session.execute(
            text(f"SELECT id, name FROM {USERS_TBL} WHERE name = :name LIMIT 1"),
            {"name": username}
        ).fetchone()
        
        if not user:
            return jsonify({"ok": False, "error": "user_not_found"}), 404
        
        # Aggregate stats with backward compatibility
        try:
            stats_row = db.session.execute(
                text(f"""
                    SELECT 
                        COUNT(id) as total_items,
                        COALESCE(AVG(proof_score), 0) as avg_proof_score,
                        SUM(CASE 
                            WHEN slice_hints_json IS NOT NULL 
                                AND slice_hints_json != '' 
                                AND slice_hints_json != '{{}}' 
                                AND LOWER(slice_hints_json) != 'null'
                            THEN 1 ELSE 0 
                        END) as presets_count
                    FROM {ITEMS_TBL}
                    WHERE author_id = :uid AND is_published = :pub
                """),
                {"uid": user.id, "pub": True}
            ).fetchone()
            
            total_items = stats_row.total_items or 0
            avg_proof_score = round(stats_row.avg_proof_score, 1) if stats_row.avg_proof_score else 0
            presets_count = stats_row.presets_count or 0
            presets_coverage = round((presets_count / total_items * 100), 1) if total_items > 0 else 0
            
        except Exception as col_err:
            # Fallback if proof_score/slice_hints columns missing
            current_app.logger.warning(f"Creator stats fallback: {col_err}")
            total_items = db.session.execute(
                text(f"SELECT COUNT(id) FROM {ITEMS_TBL} WHERE author_id = :uid AND is_published = :pub"),
                {"uid": user.id, "pub": True}
            ).scalar() or 0
            avg_proof_score = 0
            presets_coverage = 0
        
        resp = jsonify({
            "ok": True,
            "username": user.name,
            "total_items": total_items,
            "avg_proof_score": avg_proof_score,
            "presets_coverage_percent": presets_coverage
        })
        resp.headers["Cache-Control"] = "public, max-age=300"  # Cache 5 min
        return resp
        
    except Exception as e:
        current_app.logger.error(f"Get creator stats error: {e}")
        return jsonify({"ok": False, "error": "server"}), 500


@bp.get("/api/creators/stats")
def api_get_creators_stats_batch():
    """Batch endpoint: get stats for multiple creators (no N+1)"""
    try:
        users_param = request.args.get("users", "")
        if not users_param:
            return jsonify({"ok": False, "error": "missing_users_param"}), 400
        
        # Parse comma-separated usernames with strict sanitization
        import re
        raw_usernames = [u.strip() for u in users_param.split(",") if u.strip()]
        
        # Allowlist: alphanumeric, underscore, hyphen, max 50 chars
        username_pattern = re.compile(r'^[a-zA-Z0-9_-]{1,50}$')
        usernames = [u for u in raw_usernames if username_pattern.match(u)][:50]
        
        if not usernames:
            return jsonify({"ok": False, "error": "no_valid_usernames"}), 400
        
        # Single grouped query for all creators
        try:
            # First, get user_id mapping - build IN clause manually
            placeholders = ','.join([f':name{i}' for i in range(len(usernames))])
            bind_params = {f'name{i}': name for i, name in enumerate(usernames)}
            
            user_rows = db.session.execute(
                text(f"SELECT id, name FROM {USERS_TBL} WHERE name IN ({placeholders})"),
                bind_params
            ).fetchall()
            
            user_map = {row.name: row.id for row in user_rows}
            
            if not user_map:
                return jsonify({"ok": True, "stats": {}})
            
            # Grouped aggregation query - build IN clause for user_ids
            user_ids = list(user_map.values())
            id_placeholders = ','.join([f':uid{i}' for i in range(len(user_ids))])
            id_bind_params = {f'uid{i}': uid for i, uid in enumerate(user_ids)}
            id_bind_params['pub'] = True  # Postgres boolean compatibility
            
            stats_rows = db.session.execute(
                text(f"""
                    SELECT 
                        i.user_id,
                        COUNT(DISTINCT i.id) as total_items,
                        COALESCE(AVG(i.proof_score), 0) as avg_proof_score,
                        SUM(CASE 
                            WHEN i.slice_hints_json IS NOT NULL 
                                AND i.slice_hints_json != '' 
                                AND i.slice_hints_json != '{{}}' 
                                AND LOWER(i.slice_hints_json) != 'null'
                            THEN 1 ELSE 0 
                        END) as presets_count
                    FROM {ITEMS_TBL} i
                    WHERE i.user_id IN ({id_placeholders}) AND i.is_published = :pub
                    GROUP BY i.user_id
                """),
                id_bind_params
            ).fetchall()
            
            # Build stats map keyed by username
            stats_by_user_id = {}
            for row in stats_rows:
                total = row.total_items or 0
                avg_ps = round(row.avg_proof_score, 1) if row.avg_proof_score else 0
                presets_cnt = row.presets_count or 0
                coverage = round((presets_cnt / total * 100), 1) if total > 0 else 0
                
                stats_by_user_id[row.user_id] = {
                    "total_items": total,
                    "avg_proof_score": avg_ps,
                    "presets_coverage_percent": coverage
                }
            
            # Map back to usernames
            result = {}
            for username, user_id in user_map.items():
                if user_id in stats_by_user_id:
                    result[username] = stats_by_user_id[user_id]
                else:
                    # User has no published items
                    result[username] = {
                        "total_items": 0,
                        "avg_proof_score": 0,
                        "presets_coverage_percent": 0
                    }
            
        except Exception as col_err:
            # Fallback if proof_score/slice_hints columns missing
            current_app.logger.warning(f"Batch creator stats fallback: {col_err}")
            
            # Just return counts without metrics (reuse sanitized usernames)
            placeholders = ','.join([f':name{i}' for i in range(len(usernames))])
            bind_params = {f'name{i}': name for i, name in enumerate(usernames)}
            
            user_rows = db.session.execute(
                text(f"SELECT id, name FROM {USERS_TBL} WHERE name IN ({placeholders})"),
                bind_params
            ).fetchall()
            
            user_map = {row.name: row.id for row in user_rows}
            
            if user_map:
                user_ids = list(user_map.values())
                id_placeholders = ','.join([f':uid{i}' for i in range(len(user_ids))])
                id_bind_params = {f'uid{i}': uid for i, uid in enumerate(user_ids)}
                id_bind_params['pub'] = True  # Postgres boolean compatibility
                
                count_rows = db.session.execute(
                    text(f"""
                        SELECT user_id, COUNT(DISTINCT id) as total
                        FROM {ITEMS_TBL}
                        WHERE user_id IN ({id_placeholders}) AND is_published = :pub
                        GROUP BY user_id
                    """),
                    id_bind_params
                ).fetchall()
            else:
                count_rows = []
            
            counts_map = {row.user_id: row.total for row in count_rows}
            
            result = {}
            for username, user_id in user_map.items():
                result[username] = {
                    "total_items": counts_map.get(user_id, 0),
                    "avg_proof_score": None,
                    "presets_coverage_percent": None
                }
        
        resp = jsonify({"ok": True, "stats": result})
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("api_creators_stats failed: %s", e)
        return jsonify({"ok": False, "error": "server"}), 500


@bp.get("/api/user/<int:user_id>/following")
def api_get_user_following(user_id: int):
    """Get list of users this user follows"""
    try:
        # Get following (people this user follows)
        rows = db.session.execute(
            text(f"""
                SELECT u.id, u.name, COALESCE(u.avatar_url, '/static/img/user.jpg') as avatar_url
                FROM {USERS_TBL} u
                INNER JOIN user_follows uf ON uf.author_id = u.id
                WHERE uf.follower_id = :uid
                ORDER BY uf.created_at DESC
                LIMIT 50
            """),
            {"uid": user_id}
        ).fetchall()
        
        users = [{"id": r.id, "name": r.name, "avatar_url": r.avatar_url} for r in rows]
        
        resp = jsonify({"ok": True, "users": users})
        resp.headers["Cache-Control"] = "no-store"
        return resp
        
    except Exception as e:
        current_app.logger.error(f"Get following error: {e}")
        # Fallback without created_at ordering
        try:
            rows = db.session.execute(
                text(f"""
                    SELECT u.id, u.name, COALESCE(u.avatar_url, '/static/img/user.jpg') as avatar_url
                    FROM {USERS_TBL} u
                    INNER JOIN user_follows uf ON uf.author_id = u.id
                    WHERE uf.follower_id = :uid
                    ORDER BY uf.id DESC
                    LIMIT 50
                """),
                {"uid": user_id}
            ).fetchall()
            
            users = [{"id": r.id, "name": r.name, "avatar_url": r.avatar_url} for r in rows]
            resp = jsonify({"ok": True, "users": users})
            resp.headers["Cache-Control"] = "no-store"
            return resp
        except Exception as fallback_err:
            current_app.logger.error(f"Get following fallback error: {fallback_err}")
            return jsonify({"ok": False, "error": "server"}), 500


@bp.get("/api/follow/status/<int:author_id>")
def api_follow_status(author_id: int):
    """Get follow status for an author"""
    uid = _parse_int(session.get("user_id"), 0)

    followers_count = db.session.execute(
        text("SELECT COUNT(*) FROM user_follows WHERE author_id = :aid"),
        {"aid": author_id},
    ).scalar() or 0

    if not uid:
        return jsonify({"ok": True, "following": False, "followers_count": int(followers_count)})

    following = bool(db.session.execute(
        text("SELECT 1 FROM user_follows WHERE follower_id = :uid AND author_id = :aid LIMIT 1"),
        {"uid": uid, "aid": author_id},
    ).first())

    return jsonify({"ok": True, "following": following, "followers_count": int(followers_count)})


@bp.post("/api/follow/<int:author_id>")
def api_follow(author_id: int):
    """Follow an author"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if uid == author_id:
        return jsonify({"ok": False, "error": "self_follow"}), 400

    try:
        dialect = db.session.get_bind().dialect.name
        if dialect == "postgresql":
            db.session.execute(
                text("""INSERT INTO user_follows (follower_id, author_id, created_at)
                        VALUES (:uid, :aid, NOW())
                        ON CONFLICT (follower_id, author_id) DO NOTHING"""),
                {"uid": uid, "aid": author_id},
            )
        else:
            # SQLite: використовуємо INSERT OR IGNORE для уникнення дублікатів
            db.session.execute(
                text("""INSERT OR IGNORE INTO user_follows (follower_id, author_id, created_at)
                        VALUES (:uid, :aid, CURRENT_TIMESTAMP)"""),
                {"uid": uid, "aid": author_id},
            )
        db.session.commit()
        
        # Debug logging
        if current_app.debug:
            current_app.logger.info(f"POST /api/follow/{author_id}: user {uid} -> author {author_id}")
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"Follow error: {e}")

    followers_count = db.session.execute(
        text("SELECT COUNT(*) FROM user_follows WHERE author_id = :aid"),
        {"aid": author_id},
    ).scalar() or 0

    resp = jsonify({"ok": True, "following": True, "followers_count": int(followers_count)})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.delete("/api/follow/<int:author_id>")
def api_unfollow(author_id: int):
    """Unfollow an author"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    try:
        db.session.execute(
            text("DELETE FROM user_follows WHERE follower_id = :uid AND author_id = :aid"),
            {"uid": uid, "aid": author_id},
        )
        db.session.commit()
        
        # Debug logging
        if current_app.debug:
            current_app.logger.info(f"DELETE /api/follow/{author_id}: user {uid} unfollowed author {author_id}")
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500

    followers_count = db.session.execute(
        text("SELECT COUNT(*) FROM user_follows WHERE author_id = :aid"),
        {"aid": author_id},
    ).scalar() or 0

    resp = jsonify({"ok": True, "following": False, "followers_count": int(followers_count)})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/api/debug/follows")
def api_debug_follows():
    """Debug endpoint: show raw user_follows table data (only in debug mode)"""
    if not current_app.debug:
        return jsonify({"ok": False, "error": "Only available in debug mode"}), 403
    
    uid = _parse_int(session.get("user_id"), 0)
    
    try:
        # Get current user's follows
        my_follows = []
        if uid:
            rows = db.session.execute(
                text("SELECT id, follower_id, author_id, created_at FROM user_follows WHERE follower_id = :uid ORDER BY created_at DESC"),
                {"uid": uid}
            ).fetchall()
            my_follows = [{"id": r.id, "follower_id": r.follower_id, "author_id": r.author_id, "created_at": str(r.created_at)} for r in rows]
        
        # Get all follows (limit 50)
        all_rows = db.session.execute(
            text("SELECT id, follower_id, author_id, created_at FROM user_follows ORDER BY created_at DESC LIMIT 50")
        ).fetchall()
        all_follows = [{"id": r.id, "follower_id": r.follower_id, "author_id": r.author_id, "created_at": str(r.created_at)} for r in all_rows]
        
        # Get table structure
        table_info = db.session.execute(text("SELECT * FROM user_follows LIMIT 0")).keys()
        
        return jsonify({
            "ok": True,
            "current_user_id": uid,
            "my_follows": my_follows,
            "all_follows_sample": all_follows,
            "table_columns": list(table_info),
            "note": "follower_id = who follows, author_id = whom they follow"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ───────────────────────────── Feed API ─────────────────────────────
@bp.get("/api/feed/activity")
def api_feed_activity():
    """Get unified activity feed from followed authors (items, makes, reviews)"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    page = max(1, _parse_int(request.args.get("page"), 1))
    per_page = min(100, max(1, _parse_int(request.args.get("per_page"), 24)))
    offset = (page - 1) * per_page

    # Get followed authors
    try:
        followed_rows = db.session.execute(
            text("SELECT author_id FROM user_follows WHERE follower_id = :uid"),
            {"uid": uid}
        ).fetchall()
        followed_ids = [r.author_id for r in followed_rows]
        
        if not followed_ids:
            return jsonify({"ok": True, "events": [], "total": 0, "page": page, "pages": 0})
    except (sa_exc.ProgrammingError, sa_exc.OperationalError) as e:
        if _is_missing_table_error(e):
            # user_follows table doesn't exist - return empty
            return jsonify({"ok": True, "events": [], "total": 0, "page": page, "pages": 0})
        raise

    # Build events list
    events = []
    
    # 1. New items (published items from followed authors)
    try:
        dialect = db.session.get_bind().dialect.name
        items_sql = f"""
            SELECT i.id, i.title, i.cover_url, i.created_at, i.user_id,
                   u.name AS author_name,
                   COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar
            FROM {ITEMS_TBL} i
            LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
            WHERE i.user_id IN :author_ids
              AND (i.is_published IS NULL OR i.is_published = {'TRUE' if dialect == 'postgresql' else '1'})
            ORDER BY i.created_at DESC
            LIMIT 100
        """
        
        items_rows = db.session.execute(
            text(items_sql),
            {"author_ids": tuple(followed_ids)}
        ).fetchall()
        
        for r in items_rows:
            events.append({
                "type": "new_item",
                "created_at": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
                "author": {
                    "id": r.user_id,
                    "username": r.author_name or "Unknown",
                    "avatar_url": r.author_avatar
                },
                "item": {
                    "id": r.id,
                    "title": r.title,
                    "cover_url": r.cover_url or "/static/img/placeholder_stl.jpg",
                    "url": f"/item/{r.id}"
                }
            })
    except Exception as e:
        current_app.logger.error(f"New items fetch error: {e}")
    
    # 2. New makes (prints from followed authors' items)
    try:
        makes_sql = f"""
            SELECT m.id, m.image_url, m.caption, m.created_at, m.user_id,
                   i.id AS item_id, i.title AS item_title, i.cover_url AS item_cover,
                   i.user_id AS author_id,
                   u_make.name AS make_user_name,
                   u_author.name AS author_name,
                   COALESCE(u_author.avatar_url, '/static/img/user.jpg') AS author_avatar
            FROM item_makes m
            INNER JOIN {ITEMS_TBL} i ON i.id = m.item_id
            LEFT JOIN {USERS_TBL} u_make ON u_make.id = m.user_id
            LEFT JOIN {USERS_TBL} u_author ON u_author.id = i.user_id
            WHERE i.user_id IN :author_ids
            ORDER BY m.created_at DESC
            LIMIT 100
        """
        
        makes_rows = db.session.execute(
            text(makes_sql),
            {"author_ids": tuple(followed_ids)}
        ).fetchall()
        
        for r in makes_rows:
            events.append({
                "type": "new_make",
                "created_at": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
                "author": {
                    "id": r.author_id,
                    "username": r.author_name or "Unknown",
                    "avatar_url": r.author_avatar
                },
                "item": {
                    "id": r.item_id,
                    "title": r.item_title,
                    "cover_url": r.item_cover or "/static/img/placeholder_stl.jpg",
                    "url": f"/item/{r.item_id}"
                },
                "make": {
                    "id": r.id,
                    "image_url": r.image_url,
                    "caption": r.caption or "",
                    "user": {
                        "id": r.user_id,
                        "username": r.make_user_name or "Anonymous"
                    }
                }
            })
    except (sa_exc.ProgrammingError, sa_exc.OperationalError) as e:
        if not _is_missing_table_error(e):
            current_app.logger.error(f"Makes fetch error: {e}")
    
    # 3. New reviews (reviews on followed authors' items)
    try:
        # Check if review has verified status (user printed the item)
        reviews_sql = f"""
            SELECT r.id, r.rating, r.text, r.image_url, r.created_at, r.user_id,
                   i.id AS item_id, i.title AS item_title, i.cover_url AS item_cover,
                   i.user_id AS author_id,
                   u_review.name AS review_user_name,
                   u_author.name AS author_name,
                   COALESCE(u_author.avatar_url, '/static/img/user.jpg') AS author_avatar,
                   EXISTS (
                       SELECT 1 FROM item_makes m
                       WHERE m.item_id = r.item_id AND m.user_id = r.user_id
                   ) AS verified
            FROM market_reviews r
            INNER JOIN {ITEMS_TBL} i ON i.id = r.item_id
            LEFT JOIN {USERS_TBL} u_review ON u_review.id = r.user_id
            LEFT JOIN {USERS_TBL} u_author ON u_author.id = i.user_id
            WHERE i.user_id IN :author_ids
            ORDER BY r.created_at DESC
            LIMIT 100
        """
        
        reviews_rows = db.session.execute(
            text(reviews_sql),
            {"author_ids": tuple(followed_ids)}
        ).fetchall()
        
        for r in reviews_rows:
            events.append({
                "type": "new_review",
                "created_at": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
                "author": {
                    "id": r.author_id,
                    "username": r.author_name or "Unknown",
                    "avatar_url": r.author_avatar
                },
                "item": {
                    "id": r.item_id,
                    "title": r.item_title,
                    "cover_url": r.item_cover or "/static/img/placeholder_stl.jpg",
                    "url": f"/item/{r.item_id}"
                },
                "review": {
                    "id": r.id,
                    "rating": r.rating,
                    "text": r.text or "",
                    "photo_url": r.image_url,
                    "user": {
                        "id": r.user_id,
                        "username": r.review_user_name or "Anonymous"
                    },
                    "verified": bool(r.verified)
                }
            })
    except (sa_exc.ProgrammingError, sa_exc.OperationalError) as e:
        if not _is_missing_table_error(e):
            current_app.logger.error(f"Reviews fetch error: {e}")
    
    # Sort all events by created_at (most recent first)
    events.sort(key=lambda x: x["created_at"], reverse=True)
    
    # Paginate
    total = len(events)
    events_page = events[offset:offset + per_page]
    pages = math.ceil(total / per_page) if per_page > 0 else 1
    
    return jsonify({
        "ok": True,
        "events": events_page,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages
    })


@bp.get("/api/feed/following")
def api_feed_following():
    """Get items from followed authors"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    page = max(1, _parse_int(request.args.get("page"), 1))
    per_page = min(100, max(1, _parse_int(request.args.get("per_page"), 24)))
    offset = (page - 1) * per_page

    dialect = db.session.get_bind().dialect.name
    
    # ✅ Try query WITH is_published/published_at columns
    try:
        # COUNT total
        count_sql = f"""
            SELECT COUNT(DISTINCT i.id)
            FROM {ITEMS_TBL} i
            INNER JOIN user_follows uf ON i.user_id = uf.author_id
            WHERE uf.follower_id = :uid
              AND (i.is_published IS NULL OR i.is_published = {'TRUE' if dialect == 'postgresql' else '1'})
        """
        total = db.session.execute(text(count_sql), {"uid": uid}).scalar() or 0
        
        # SELECT items
        items_sql = f"""
            SELECT i.id, i.title, i.price, i.tags, i.cover_url, i.user_id,
                   i.rating, i.downloads, i.format, i.created_at,
                   i.is_published, i.published_at,
                   COALESCE(i.published_at, i.created_at) as sort_date
            FROM {ITEMS_TBL} i
            INNER JOIN user_follows uf ON i.user_id = uf.author_id
            WHERE uf.follower_id = :uid
              AND (i.is_published IS NULL OR i.is_published = {'TRUE' if dialect == 'postgresql' else '1'})
            ORDER BY sort_date DESC
            LIMIT :limit OFFSET :offset
        """
        
        rows = db.session.execute(
            text(items_sql),
            {"uid": uid, "limit": per_page, "offset": offset}
        ).fetchall()
        
        items = [_item_to_dict(_row_to_dict(r)) for r in rows]
        pages = math.ceil(total / per_page) if per_page > 0 else 1
        
        return jsonify({
            "ok": True,
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages
        })
        
    except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
        # 🔄 FALLBACK: Column doesn't exist yet (old schema)
        if _is_missing_column_error(e):
            db.session.rollback()
            
            try:
                # COUNT without is_published filter
                count_sql_fallback = f"""
                    SELECT COUNT(DISTINCT i.id)
                    FROM {ITEMS_TBL} i
                    INNER JOIN user_follows uf ON i.user_id = uf.author_id
                    WHERE uf.follower_id = :uid
                """
                total = db.session.execute(text(count_sql_fallback), {"uid": uid}).scalar() or 0
                
                # SELECT items without is_published/published_at
                items_sql_fallback = f"""
                    SELECT i.id, i.title, i.price, i.tags, i.cover_url, i.user_id,
                           i.rating, i.downloads, i.format, i.created_at
                    FROM {ITEMS_TBL} i
                    INNER JOIN user_follows uf ON i.user_id = uf.author_id
                    WHERE uf.follower_id = :uid
                    ORDER BY i.created_at DESC
                    LIMIT :limit OFFSET :offset
                """
                
                rows = db.session.execute(
                    text(items_sql_fallback),
                    {"uid": uid, "limit": per_page, "offset": offset}
                ).fetchall()
                
                items = [_item_to_dict(_row_to_dict(r)) for r in rows]
                pages = math.ceil(total / per_page) if per_page > 0 else 1
                
                return jsonify({
                    "ok": True,
                    "items": items,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "pages": pages
                })
            except Exception as fallback_err:
                current_app.logger.error(f"Feed fallback error: {fallback_err}")
                return jsonify({"ok": False, "error": "server", "detail": str(fallback_err)}), 500
        else:
            current_app.logger.error(f"Feed following error: {e}")
            return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500
    except Exception as e:
        current_app.logger.error(f"Feed following error: {e}")
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


@bp.post("/api/item/<int:item_id>/delete")
def api_item_delete(item_id: int):
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        res = db.session.execute(
            text(f"DELETE FROM {ITEMS_TBL} WHERE id = :id AND user_id = :uid"),
            {"id": item_id, "uid": uid}
        )
        db.session.commit()
        if res.rowcount == 0:
            return jsonify({"ok": False, "error": "not_found_or_forbidden"}), 403
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


# ───────────────────────────── TOP PRINTS API ─────────────────────────────
@bp.get("/api/top-prints")
def api_top_prints():
    """Top Prints Leaderboard: items + top authors by prints count"""
    try:
        # 🔍 DIAGNOSTIC: Log incoming params
        current_app.logger.info(f"[TOP_PRINTS] Query params: range={request.args.get('range')}, page={request.args.get('page')}, per_page={request.args.get('per_page')}")
        
        range_param = (request.args.get("range") or "all").lower()
        range_param = range_param if range_param in ("all", "7d", "30d") else "all"
        
        page = max(1, _parse_int(request.args.get("page"), 1))
        per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))
        offset = (page - 1) * per_page
        
        current_app.logger.info(f"[TOP_PRINTS] Parsed: range={range_param}, page={page}, per_page={per_page}, offset={offset}")
        
        dialect = db.session.get_bind().dialect.name
        
        # Determine date filter for trending
        date_filter = ""
        if range_param == "7d":
            if dialect == "postgresql":
                date_filter = "WHERE m.created_at >= NOW() - INTERVAL '7 days'"
            else:  # SQLite
                date_filter = "WHERE m.created_at >= datetime('now', '-7 days')"
        elif range_param == "30d":
            if dialect == "postgresql":
                date_filter = "WHERE m.created_at >= NOW() - INTERVAL '30 days'"
            else:  # SQLite
                date_filter = "WHERE m.created_at >= datetime('now', '-30 days')"
        
        # Try to fetch top items with prints count
        try:
            # Fetch top models
            if dialect == "postgresql":
                url_expr = "i.stl_main_url"
            else:
                url_expr = "i.stl_main_url"
            
            sql_items = f"""
                SELECT i.id, i.title, i.price, i.tags,
                       COALESCE(i.cover_url, '') AS cover_url,
                       COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                       COALESCE(i.rating, 0) AS rating,
                       COALESCE(i.downloads, 0) AS downloads,
                       {url_expr} AS url,
                       i.format, i.user_id, i.created_at,
                       COALESCE(pm.prints_count, 0) AS prints_count,
                       u.name AS author_name,
                       COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar
                FROM {ITEMS_TBL} i
                LEFT JOIN (
                    SELECT item_id, COUNT(*) AS prints_count
                    FROM item_makes m
                    {date_filter}
                    GROUP BY item_id
                ) pm ON pm.item_id = i.id
                LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                WHERE COALESCE(pm.prints_count, 0) > 0
                ORDER BY prints_count DESC, i.created_at DESC
                LIMIT :limit OFFSET :offset
            """
            
            rows = db.session.execute(
                text(sql_items),
                {"limit": per_page, "offset": offset}
            ).fetchall()
            
            items = [_item_to_dict(_row_to_dict(r)) for r in rows]
            
            # Fetch top authors (sum of prints across all their items)
            top_authors = []
            try:
                sql_authors = f"""
                    SELECT u.id, u.name, 
                           COALESCE(u.avatar_url, '/static/img/user.jpg') AS avatar_url,
                           COUNT(DISTINCT m.id) AS total_prints,
                           COUNT(DISTINCT i.id) AS items_count
                FROM {USERS_TBL} u
                INNER JOIN {ITEMS_TBL} i ON i.user_id = u.id
                INNER JOIN item_makes m ON m.item_id = i.id
                {date_filter.replace('WHERE', 'WHERE' if not date_filter else 'AND')}
                GROUP BY u.id, u.name, u.avatar_url
                HAVING COUNT(DISTINCT m.id) > 0
                ORDER BY total_prints DESC
                LIMIT 10
            """
            
                author_rows = db.session.execute(text(sql_authors)).fetchall()
                for ar in author_rows:
                    top_authors.append({
                        "id": ar.id,
                        "name": ar.name,
                        "avatar_url": ar.avatar_url,
                        "total_prints": ar.total_prints,
                        "items_count": ar.items_count,
                    })
            except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e_auth:
                # Graceful fallback if table doesn't exist
                current_app.logger.warning(f"[TOP_PRINTS] Authors query failed: {type(e_auth).__name__}: {e_auth}")
                if _is_missing_table_error(e_auth):
                    current_app.logger.info("[TOP_PRINTS] Fallback: top_authors = [] (missing table)")
                    top_authors = []
                else:
                    raise  # Re-raise if not a missing table error
            
            # Total count for pagination
            sql_total = f"""
                SELECT COUNT(DISTINCT i.id)
                FROM {ITEMS_TBL} i
                INNER JOIN item_makes m ON m.item_id = i.id
                {date_filter}
            """
            total = db.session.execute(text(sql_total)).scalar() or 0
            
            return jsonify({
                "ok": True,
                "items": items,
                "top_authors": top_authors,
                "range": range_param,
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": math.ceil(total / per_page) if per_page else 1,
            })
            
        except (sa_exc.OperationalError, sa_exc.ProgrammingError) as e:
            # Fallback: item_makes table doesn't exist - show top by downloads instead
            current_app.logger.warning(f"[TOP_PRINTS] Main query failed: {type(e).__name__}: {e}")
            if _is_missing_table_error(e):
                current_app.logger.info("[TOP_PRINTS] Fallback: Using downloads-based query (missing item_makes)")
                db.session.rollback()
                
                # Get top items by downloads (no prints data available)
                dialect = db.session.get_bind().dialect.name
                if dialect == "postgresql":
                    url_expr = "i.stl_main_url"
                else:
                    url_expr = "i.stl_main_url"
                
                sql_fallback = f"""
                    SELECT i.id, i.title, i.price, i.tags,
                           COALESCE(i.cover_url, '') AS cover_url,
                           COALESCE(i.gallery_urls, '[]') AS gallery_urls,
                           COALESCE(i.rating, 0) AS rating,
                           COALESCE(i.downloads, 0) AS downloads,
                           {url_expr} AS url,
                           i.format, i.user_id, i.created_at,
                           0 AS prints_count,
                           u.name AS author_name,
                           COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar
                    FROM {ITEMS_TBL} i
                    LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
                    ORDER BY i.downloads DESC, i.created_at DESC
                    LIMIT :limit OFFSET :offset
                """
                
                fallback_rows = db.session.execute(
                    text(sql_fallback),
                    {"limit": per_page, "offset": offset}
                ).fetchall()
                
                fallback_items = [_item_to_dict(_row_to_dict(r)) for r in fallback_rows]
                
                # Total count
                total_fallback = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {ITEMS_TBL}")
                ).scalar() or 0
                
                return jsonify({
                    "ok": True,
                    "items": fallback_items,
                    "top_authors": [],
                    "range": range_param,
                    "page": page,
                    "per_page": per_page,
                    "total": total_fallback,
                    "pages": math.ceil(total_fallback / per_page) if per_page else 1,
                })
            else:
                current_app.logger.error(f"[TOP_PRINTS] Non-fallback DB error, re-raising")
                raise
                
    except Exception as e:
        # 🔍 DIAGNOSTIC: Log full exception with traceback (only in debug mode)
        import traceback
        current_app.logger.exception(f"[TOP_PRINTS] FATAL ERROR: {type(e).__name__}: {e}")
        if current_app.debug:
            # Only log full traceback in debug mode to avoid log spam in production
            current_app.logger.error(f"[TOP_PRINTS] Traceback:\n{traceback.format_exc()}")
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


# ───────────────────────────── MAKES API ─────────────────────────────
@bp.get("/api/item/<int:item_id>/makes")
def api_get_makes(item_id: int):
    """Get all makes (printed photos) for an item"""
    limit = min(24, max(1, _parse_int(request.args.get("limit"), 12)))
    offset = max(0, _parse_int(request.args.get("offset"), 0))
    
    uid = _parse_int(session.get("user_id"), 0)
    
    try:
        dialect = db.session.get_bind().dialect.name
        
        # Handle verified column - may not exist yet or different types (BOOLEAN/INTEGER)
        if dialect == "postgresql":
            verified_expr = "COALESCE(m.verified, FALSE)"
        else:
            # SQLite: INTEGER (0/1), convert to boolean-like
            verified_expr = "COALESCE(m.verified, 0)"
        
        # Fetch makes with author info via JOIN
        sql = f"""
            SELECT m.id, m.item_id, m.user_id, m.image_url, m.caption, m.created_at,
                   {verified_expr} AS verified,
                   u.name AS author_name,
                   COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar
            FROM item_makes m
            LEFT JOIN {USERS_TBL} u ON u.id = m.user_id
            WHERE m.item_id = :item_id
            ORDER BY m.created_at DESC
            LIMIT :limit OFFSET :offset
        """
        
        rows = db.session.execute(
            text(sql),
            {"item_id": item_id, "limit": limit, "offset": offset}
        ).fetchall()
        
        makes = []
        for r in rows:
            d = _row_to_dict(r)
            d["is_owner"] = (d.get("user_id") == uid)
            # Ensure verified is boolean (SQLite returns 0/1)
            if "verified" in d:
                d["verified"] = bool(d["verified"])
            else:
                d["verified"] = False
            makes.append(d)
        
        return jsonify({"ok": True, "makes": makes})
        
    except sa_exc.OperationalError as e:
        # Handle case where verified column doesn't exist yet
        if "no such column" in str(e).lower() or "column" in str(e).lower():
            current_app.logger.warning(f"Makes API: verified column not ready: {e}")
            # Retry without verified column
            try:
                sql_fallback = f"""
                    SELECT m.id, m.item_id, m.user_id, m.image_url, m.caption, m.created_at,
                           u.name AS author_name,
                           COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar
                    FROM item_makes m
                    LEFT JOIN {USERS_TBL} u ON u.id = m.user_id
                    WHERE m.item_id = :item_id
                    ORDER BY m.created_at DESC
                    LIMIT :limit OFFSET :offset
                """
                rows = db.session.execute(
                    text(sql_fallback),
                    {"item_id": item_id, "limit": limit, "offset": offset}
                ).fetchall()
                
                makes = []
                for r in rows:
                    d = _row_to_dict(r)
                    d["is_owner"] = (d.get("user_id") == uid)
                    d["verified"] = False  # Default when column missing
                    makes.append(d)
                
                return jsonify({"ok": True, "makes": makes})
            except Exception as retry_err:
                current_app.logger.error(f"Makes API fallback failed: {retry_err}")
                return jsonify({"ok": False, "error": "server"}), 500
        else:
            raise
    except Exception as e:
        current_app.logger.error(f"Get makes error: {e}")
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


@bp.post("/api/item/<int:item_id>/makes")
def api_create_make(item_id: int):
    """Upload a new make (printed photo) for an item"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    
    try:
        # Validate item exists
        item_check = db.session.execute(
            text(f"SELECT id FROM {ITEMS_TBL} WHERE id = :id"),
            {"id": item_id}
        ).fetchone()
        
        if not item_check:
            return jsonify({"ok": False, "error": "item_not_found"}), 404
        
        # Get uploaded image
        image_file = request.files.get("image")
        if not image_file:
            return jsonify({"ok": False, "error": "missing_image"}), 400
        
        # Save image using existing _save_upload
        image_url = _save_upload(image_file, f"user_{uid}/makes", ALLOWED_IMAGE_EXT)
        if not image_url:
            return jsonify({"ok": False, "error": "invalid_image"}), 400
        
        # Get optional caption
        caption = (request.form.get("caption") or "").strip()
        if len(caption) > 500:
            caption = caption[:500]
        
        # Insert into item_makes and fetch created row
        dialect = db.session.get_bind().dialect.name
        
        if dialect == "postgresql":
            # PostgreSQL: use RETURNING to get created row directly (no race condition)
            sql = f"""
                INSERT INTO item_makes (item_id, user_id, image_url, caption)
                VALUES (:item_id, :user_id, :image_url, :caption)
                RETURNING id
            """
            result = db.session.execute(
                text(sql),
                {
                    "item_id": item_id,
                    "user_id": uid,
                    "image_url": image_url,
                    "caption": caption or None
                }
            )
            db.session.commit()
            
            # Get returned ID
            make_id = result.fetchone()[0]
            
        else:
            # SQLite: use lastrowid
            sql = """
                INSERT INTO item_makes (item_id, user_id, image_url, caption)
                VALUES (:item_id, :user_id, :image_url, :caption)
            """
            result = db.session.execute(
                text(sql),
                {
                    "item_id": item_id,
                    "user_id": uid,
                    "image_url": image_url,
                    "caption": caption or None
                }
            )
            db.session.commit()
            make_id = result.lastrowid
        
        # Fetch created make with author info
        make_row = db.session.execute(
            text(f"""
                SELECT m.id, m.item_id, m.user_id, m.image_url, m.caption, m.created_at,
                       u.name AS author_name,
                       COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar
                FROM item_makes m
                LEFT JOIN {USERS_TBL} u ON u.id = m.user_id
                WHERE m.id = :id
            """),
            {"id": make_id}
        ).fetchone()
        
        if make_row:
            make_dict = _row_to_dict(make_row)
            make_dict["is_owner"] = True
            return jsonify({"ok": True, "make": make_dict})
        else:
            # Fallback if fetch failed
            return jsonify({"ok": True, "make": {"image_url": image_url, "caption": caption}})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Create make error: {e}")
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


@bp.delete("/api/make/<int:make_id>")
def api_delete_make(make_id: int):
    """Delete a make - only owner can delete"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    
    try:
        # Delete only if user_id matches
        result = db.session.execute(
            text("DELETE FROM item_makes WHERE id = :id AND user_id = :uid"),
            {"id": make_id, "uid": uid}
        )
        db.session.commit()
        
        if result.rowcount == 0:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        
        return jsonify({"ok": True})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Delete make error: {e}")
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


# ───────────────────────────── REVIEWS API v2 ─────────────────────────────
def recalc_item_rating(item_id: int):
    """
    Recalculate and update item rating based on reviews.
    Updates items.rating and ratings_cnt (if column exists).
    """
    try:
        # Calculate AVG and COUNT from reviews
        stats_sql = """
            SELECT AVG(rating) as avg_rating, COUNT(*) as count
            FROM market_reviews
            WHERE item_id = :item_id
        """
        stats = db.session.execute(text(stats_sql), {"item_id": item_id}).fetchone()
        
        avg_rating = float(stats[0]) if stats and stats[0] else 0.0
        review_count = int(stats[1]) if stats and stats[1] else 0
        
        # Check if ratings_cnt column exists
        dialect = db.session.get_bind().dialect.name
        has_ratings_cnt = False
        
        try:
            # Quick check for column existence
            db.session.execute(text(f"SELECT ratings_cnt FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            has_ratings_cnt = True
        except (sa_exc.OperationalError, sa_exc.ProgrammingError):
            db.session.rollback()
        
        # Update rating (with or without ratings_cnt)
        if has_ratings_cnt:
            update_sql = f"""
                UPDATE {ITEMS_TBL}
                SET rating = :rating, ratings_cnt = :count
                WHERE id = :item_id
            """
            db.session.execute(
                text(update_sql),
                {"rating": avg_rating, "count": review_count, "item_id": item_id}
            )
        else:
            update_sql = f"""
                UPDATE {ITEMS_TBL}
                SET rating = :rating
                WHERE id = :item_id
            """
            db.session.execute(
                text(update_sql),
                {"rating": avg_rating, "item_id": item_id}
            )
        
        db.session.commit()
        current_app.logger.info(f"✅ Recalculated rating for item {item_id}: {avg_rating:.2f} ({review_count} reviews)")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Recalc rating error for item {item_id}: {e}")


@bp.get("/api/item/<int:item_id>/reviews")
def api_get_reviews(item_id: int):
    """Get reviews for an item with author info + verified badge"""
    limit = min(50, max(1, _parse_int(request.args.get("limit"), 50)))
    
    uid = _parse_int(session.get("user_id"), 0)
    
    try:
        # Fetch reviews with author info + verified check
        # Using subquery to avoid duplicates if user has multiple makes
        sql = f"""
            SELECT r.id, r.user_id, r.item_id, r.rating, r.text, r.image_url, r.created_at,
                   u.name AS author_name,
                   COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM item_makes m 
                       WHERE m.item_id = r.item_id AND m.user_id = r.user_id
                   ) THEN 1 ELSE 0 END AS verified
            FROM market_reviews r
            LEFT JOIN {USERS_TBL} u ON u.id = r.user_id
            WHERE r.item_id = :item_id
            ORDER BY r.created_at DESC
            LIMIT :limit
        """
        
        rows = db.session.execute(
            text(sql),
            {"item_id": item_id, "limit": limit}
        ).fetchall()
        
        reviews = []
        for r in rows:
            d = _row_to_dict(r)
            d["is_owner"] = (d.get("user_id") == uid)
            d["verified"] = bool(d.get("verified", 0))
            reviews.append(d)
        
        return jsonify({"ok": True, "reviews": reviews})
        
    except Exception as e:
        current_app.logger.error(f"Get reviews error: {e}")
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


@bp.post("/api/item/<int:item_id>/reviews")
def api_create_review(item_id: int):
    """Create a new review for an item"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    
    try:
        # Validate item exists
        item_check = db.session.execute(
            text(f"SELECT id FROM {ITEMS_TBL} WHERE id = :id"),
            {"id": item_id}
        ).fetchone()
        
        if not item_check:
            return jsonify({"ok": False, "error": "item_not_found"}), 404
        
        # Check if user already reviewed this item (prevent duplicate reviews)
        existing_review = db.session.execute(
            text("SELECT id FROM market_reviews WHERE item_id = :item_id AND user_id = :uid"),
            {"item_id": item_id, "uid": uid}
        ).fetchone()
        
        if existing_review:
            return jsonify({"ok": False, "error": "already_reviewed"}), 400
        
        # Get rating (required)
        rating = _parse_int(request.form.get("rating"), 0)
        if rating < 1 or rating > 5:
            return jsonify({"ok": False, "error": "invalid_rating"}), 400
        
        # Get text (optional)
        text = (request.form.get("text") or "").strip()
        if len(text) > 1000:
            text = text[:1000]
        
        # Get optional image
        image_url = None
        image_file = request.files.get("image")
        if image_file:
            image_url = _save_upload(image_file, f"user_{uid}/reviews", ALLOWED_IMAGE_EXT)
        
        # Insert review (same SQL for both dialects)
        sql = """
            INSERT INTO market_reviews (item_id, user_id, rating, text, image_url)
            VALUES (:item_id, :user_id, :rating, :text, :image_url)
        """
        db.session.execute(
            text(sql),
            {
                "item_id": item_id,
                "user_id": uid,
                "rating": rating,
                "text": text or None,
                "image_url": image_url
            }
        )
        db.session.commit()
        
        # Recalculate item rating
        recalc_item_rating(item_id)
        
        return jsonify({"ok": True})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Create review error: {e}")
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


@bp.delete("/api/review/<int:review_id>")
def api_delete_review(review_id: int):
    """Delete a review - only owner can delete"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    
    try:
        # Get item_id before delete (for recalc)
        review = db.session.execute(
            text("SELECT item_id FROM market_reviews WHERE id = :id AND user_id = :uid"),
            {"id": review_id, "uid": uid}
        ).fetchone()
        
        if not review:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        
        item_id = review[0]
        
        # Delete review
        db.session.execute(
            text("DELETE FROM market_reviews WHERE id = :id"),
            {"id": review_id}
        )
        db.session.commit()
        
        # Recalculate item rating
        recalc_item_rating(item_id)
        
        return jsonify({"ok": True})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Delete review error: {e}")
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


@bp.post("/api/item/<int:item_id>/publish")
def api_item_publish(item_id: int):
    """Toggle is_published status and set published_at timestamp on first publish"""
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    
    dialect = db.session.get_bind().dialect.name
    
    try:
        # Get current status
        row = db.session.execute(
            text(f"SELECT is_published FROM {ITEMS_TBL} WHERE id = :id AND user_id = :uid"),
            {"id": item_id, "uid": uid}
        ).fetchone()
        
        if not row:
            return jsonify({"ok": False, "error": "not_found_or_forbidden"}), 403
        
        current_status = bool(row[0]) if row[0] is not None else False
        new_status = not current_status
        
        # Update is_published and published_at
        if new_status:
            # Publishing: set is_published=true and published_at=now
            if dialect == "postgresql":
                sql = f"""
                    UPDATE {ITEMS_TBL}
                    SET is_published = TRUE,
                        published_at = COALESCE(published_at, NOW()),
                        updated_at = NOW()
                    WHERE id = :id AND user_id = :uid
                """
            else:
                sql = f"""
                    UPDATE {ITEMS_TBL}
                    SET is_published = TRUE,
                        published_at = COALESCE(published_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND user_id = :uid
                """
        else:
            # Unpublishing: set is_published=false, keep published_at
            if dialect == "postgresql":
                sql = f"""
                    UPDATE {ITEMS_TBL}
                    SET is_published = FALSE,
                        updated_at = NOW()
                    WHERE id = :id AND user_id = :uid
                """
            else:
                sql = f"""
                    UPDATE {ITEMS_TBL}
                    SET is_published = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND user_id = :uid
                """
        
        res = db.session.execute(text(sql), {"id": item_id, "uid": uid})
        db.session.commit()
        
        if res.rowcount == 0:
            return jsonify({"ok": False, "error": "not_found_or_forbidden"}), 403
        
        return jsonify({"ok": True, "is_published": new_status})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


@bp.post("/api/item/<int:item_id>/update")
def api_item_update(item_id: int):
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form or {}

    fields: Dict[str, Any] = {}

    # Handle file uploads if present
    if request.files:
        # Handle cover image upload (accept both 'cover' and 'cover_file')
        cover_file = request.files.get("cover") or request.files.get("cover_file")
        if cover_file:
            cover_url = _save_upload(cover_file, "covers", ALLOWED_IMAGE_EXT)
            if cover_url:
                fields["cover_url"] = cover_url

        # Handle gallery images upload (accept both 'new_images' and 'gallery_files')
        new_images = request.files.getlist("new_images") or request.files.getlist("gallery_files")
        if new_images:
            # Get existing gallery
            try:
                existing_row = db.session.execute(
                    text(f"SELECT gallery_urls FROM {ITEMS_TBL} WHERE id = :id AND user_id = :uid"),
                    {"id": item_id, "uid": uid}
                ).first()
                if existing_row:
                    existing_gallery = _safe_json_list(existing_row[0])
                else:
                    existing_gallery = []
            except Exception:
                existing_gallery = []

            # Upload new images (limit to 6 uploads)
            uploaded_urls = []
            for img in new_images[:6]:
                img_url = _save_upload(img, "gallery", ALLOWED_IMAGE_EXT)
                if img_url:
                    uploaded_urls.append(img_url)

            # Merge with existing, limit total to 10
            merged_gallery = existing_gallery + uploaded_urls
            merged_gallery = merged_gallery[:10]
            fields["gallery_urls"] = json_dumps_safe(merged_gallery)

            # If new gallery uploaded and cover not provided, set cover to first new image
            if uploaded_urls and "cover_url" not in fields:
                fields["cover_url"] = uploaded_urls[0]

        # Handle STL file upload (accept both 'stl' and 'stl_file')
        stl_file = request.files.get("stl") or request.files.get("stl_file")
        if stl_file:
            stl_url = _save_upload(stl_file, "models", ALLOWED_MODEL_EXT)
            if stl_url:
                fields["stl_main_url"] = stl_url

    if "title" in data:
        fields["title"] = (data.get("title") or "").strip()

    if "desc" in data or "description" in data:
        fields['"description"'] = (data.get("desc") or data.get("description") or "").strip()

    if "price" in data:
        fields["price"] = _parse_int(data.get("price"), 0)

    if "tags" in data:
        tags_val = data.get("tags")
        if isinstance(tags_val, list):
            tags_str = ",".join([str(t).strip() for t in tags_val if str(t).strip()])
        else:
            # Safe parsing - try as JSON array first, then treat as string
            val = _safe_json_list(tags_val) if isinstance(tags_val, str) and tags_val.strip().startswith("[") else tags_val
            if isinstance(val, list):
                tags_str = ",".join([str(t).strip() for t in val if str(t).strip()])
            else:
                tags_str = str(val or "")
        fields["tags"] = tags_str

    if "category" in data:
        fields["category"] = (data.get("category") or "").strip()

    if "cover" in data or "cover_url" in data:
        cv = (data.get("cover_url") or data.get("cover") or "").strip()
        if cv and "cover_url" not in fields:  # Only if there's a value and no file upload
            fields["cover_url"] = cv

    if "gallery_urls" in data or "photos" in data:
        g_val = data.get("gallery_urls") or data.get("photos")
        g_list = _safe_json_list(g_val) if isinstance(g_val, str) else (g_val if isinstance(g_val, list) else [])
        g_list = [str(x) for x in g_list if x]
        if "gallery_urls" not in fields:  # Only if not already set by file upload
            fields["gallery_urls"] = json_dumps_safe(g_list)

    if "stl_main_url" in data or "url" in data or "file_url" in data:
        url_val = (data.get("stl_main_url") or data.get("url") or data.get("file_url") or "").strip()
        if url_val and "stl_main_url" not in fields:  # Only if not already set by file upload
            fields["stl_main_url"] = url_val

    if "stl_extra_urls" in data or "stl_files" in data:
        s_val = data.get("stl_extra_urls") or data.get("stl_files")
        s_list = _safe_json_list(s_val) if isinstance(s_val, str) else (s_val if isinstance(s_val, list) else [])
        s_list = [str(x) for x in s_list if x]
        fields["stl_extra_urls"] = json_dumps_safe(s_list)

    if "zip_url" in data:
        fields["zip_url"] = (data.get("zip_url") or "").strip()

    if "format" in data:
        fields["format"] = (data.get("format") or "stl").strip().lower()

    if not fields:
        return jsonify({"ok": False, "error": "no_fields"}), 400

    dialect = db.session.get_bind().dialect.name
    set_clauses = []
    params: Dict[str, Any] = {"id": item_id, "uid": uid}

    for col, val in fields.items():
        if col.startswith('"') and col.endswith('"'):
            key = col.strip('"')
            set_clauses.append(f'"{key}" = :{key}')
            params[key] = val
        else:
            set_clauses.append(f"{col} = :{col}")
            params[col] = val

    if dialect == "postgresql":
        set_clauses.append("updated_at = NOW()")
    else:
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")

    sql = f"""
        UPDATE {ITEMS_TBL}
        SET {", ".join(set_clauses)}
        WHERE id = :id AND user_id = :uid
    """

    try:
        res = db.session.execute(text(sql), params)
        db.session.commit()
        if res.rowcount == 0:
            return jsonify({"ok": False, "error": "not_found_or_forbidden"}), 403
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500


# ───────────────────────────── Compatibility routes for edit_model.js ─────────────────────────────
@bp.post("/api/market/update/<int:item_id>")
def api_market_update_compat(item_id: int):
    """Proxy route for /api/market/update/<id> → api_item_update"""
    return api_item_update(item_id)


@bp.post("/api/market/upload/<int:item_id>")
def api_market_upload_compat(item_id: int):
    """Proxy route for /api/market/upload/<id> → api_item_update"""
    return api_item_update(item_id)


# ───────────────────────────── HTML form delete route ─────────────────────────────
@bp.post("/market/delete/<int:item_id>")
def market_delete_form(item_id: int):
    """HTML form delete route that redirects after calling api_item_delete"""
    result = api_item_delete(item_id)
    # Check if delete was successful
    if isinstance(result, tuple):
        response, status_code = result
    else:
        response = result
        status_code = 200
    
    # If successful (2xx status), redirect to market page
    if 200 <= status_code < 300:
        return redirect(url_for('market.page_market', owner='me'))
    
    # If failed, return the JSON error
    return result


@bp.post("/api/upload")
def api_upload():
    # ✅ FIX: uid/user_id визначаємо ПЕРЕД тим, як зберігати файли
    # щоб не було user_0 і “після деплою пропало”
    uid = _parse_int(session.get("user_id"), 0)

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        form, files = request.form, request.files

        # якщо фронт шле user_id — приймемо, але пріоритет у session
        form_uid = _parse_int(form.get("user_id"), 0)
        if not uid and form_uid:
            uid = form_uid

        if not uid:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        title = (form.get("title") or "").strip()

        # ✅ FIX: підтримка price_cents з фронта (зберігаємо в БД як price)
        # - якщо є price -> як і було
        # - якщо немає price, але є price_cents -> конвертуємо в PLN (ціле)
        price = _parse_int(form.get("price"), 0)
        if not price:
            price_cents = _parse_int(form.get("price_cents"), 0)
            if price_cents:
                # БД у тебе integer price (PLN). Робимо нормальне округлення.
                price = int(round(price_cents / 100.0))

        # ✅ FIX: підтримка description з фронта (мапаємо в desc)
        desc = (form.get("desc") or form.get("description") or "").strip()

        fmt = (form.get("format") or "stl").strip().lower()

        raw_tags = form.get("tags") or ""
        # Safe tags parsing - can be JSON array or CSV string
        if raw_tags.strip().startswith("["):
            tags_val = _safe_json_list(raw_tags)
        else:
            tags_val = raw_tags

        file_url = (form.get("stl_url") or (form.get("url") or "")).strip()
        zip_url = (form.get("zip_url") or "").strip()

        stl_extra_files = files.getlist("stl_files") if "stl_files" in files else []
        stl_urls = []

        # Accept multiple field names for compatibility
        if not file_url:
            if "stl_file" in files:
                saved = _save_upload(files["stl_file"], f"user_{uid}/models", ALLOWED_MODEL_EXT)
                if saved:
                    file_url = saved
            elif "file" in files:
                saved = _save_upload(files["file"], f"user_{uid}/models", ALLOWED_MODEL_EXT)
                if saved:
                    file_url = saved
            elif "files" in files:
                fls = files.getlist("files")
                if fls:
                    saved = _save_upload(fls[0], f"user_{uid}/models", ALLOWED_MODEL_EXT)
                    if saved:
                        file_url = saved

        if not zip_url and "zip_file" in files:
            saved_zip = _save_upload(files["zip_file"], f"user_{uid}/zips", ALLOWED_ARCHIVE_EXT)
            if saved_zip:
                zip_url = saved_zip

        if stl_extra_files:
            for f in stl_extra_files[:5]:
                saved = _save_upload(f, f"user_{uid}/models", ALLOWED_MODEL_EXT)
                if saved:
                    stl_urls.append(saved)

        cover = (form.get("cover_url") or "").strip()
        gallery_files = files.getlist("gallery_files") if "gallery_files" in files else []
        images = []

        # ✅ FIX: підтримка cover як file під ключем "cover" (HTML: name="cover")
        # + лишаємо стару сумісність cover_file
        if not cover:
            if "cover" in files:
                saved = _save_upload(files["cover"], f"user_{uid}/covers", ALLOWED_IMAGE_EXT)
                if saved:
                    cover = saved
            elif "cover_file" in files:
                saved = _save_upload(files["cover_file"], f"user_{uid}/covers", ALLOWED_IMAGE_EXT)
                if saved:
                    cover = saved

        if gallery_files:
            for f in gallery_files[:5]:
                saved = _save_upload(f, f"user_{uid}/gallery", ALLOWED_IMAGE_EXT)
                if saved:
                    images.append(saved)

        user_id = uid  # ✅ FIX: для INSERT в БД

    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()

        # ✅ FIX: підтримка price_cents в JSON також
        price = _parse_int(data.get("price"), 0)
        if not price:
            price_cents = _parse_int(data.get("price_cents"), 0)
            if price_cents:
                price = int(round(price_cents / 100.0))

        # ✅ FIX: підтримка description в JSON також
        desc = (data.get("desc") or data.get("description") or "").strip()

        fmt = (data.get("format") or "stl").strip().lower()
        file_url = (data.get("url") or data.get("file_url") or data.get("stl_url") or "").strip()
        zip_url = (data.get("zip_url") or "").strip()
        cover = (data.get("cover") or data.get("cover_url") or "").strip()
        tags_val = data.get("tags") or ""
        user_id = _parse_int(data.get("user_id"), 0) or uid

        if not user_id:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        photos_data = data.get("photos")
        if isinstance(photos_data, dict):
            images = list(photos_data.get("images", []))
            stl_urls = list(photos_data.get("stl", []))
        else:
            images = list(data.get("photos") or data.get("gallery_urls") or [])
            stl_urls = list(data.get("stl_files") or data.get("stl_extra_urls") or [])

    # ✅ FIX: якщо cover порожній, але є gallery — беремо перше фото
    if not cover and images:
        cover = images[0]
    if not cover:
        cover = COVER_PLACEHOLDER

    if isinstance(tags_val, list):
        tags_str = ",".join([str(t).strip() for t in tags_val if str(t).strip()])
    else:
        tags_str = str(tags_val or "")

    if not title or not file_url or not user_id:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    images = (images or [])[:5]
    stl_urls = (stl_urls or [])[:5]
    gallery_json = json_dumps_safe(images)
    stl_extra_json = json_dumps_safe(stl_urls)

    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        sql = f"""
            INSERT INTO {ITEMS_TBL}
              (title, "description", price, tags,
               cover_url, gallery_urls,
               stl_main_url, stl_extra_urls,
               zip_url,
               format,
               downloads, user_id, created_at, updated_at)
            VALUES
              (:title, :desc, :price, :tags,
               :cover_url, :gallery_urls,
               :stl_main_url, :stl_extra_urls,
               :zip_url,
               :format,
               0, :user_id, NOW(), NOW())
            RETURNING id
        """
    else:
        sql = f"""
            INSERT INTO {ITEMS_TBL}
              (title, "description", price, tags,
               cover_url, gallery_urls,
               stl_main_url, stl_extra_urls,
               zip_url,
               format,
               downloads, user_id, created_at, updated_at)
            VALUES
              (:title, :desc, :price, :tags,
               :cover_url, :gallery_urls,
               :stl_main_url, :stl_extra_urls,
               :zip_url,
               :format,
               0, :user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

    row = db.session.execute(
        text(sql),
        {
            "title": title,
            "desc": desc,
            "price": price,
            "tags": tags_str,
            "cover_url": cover,
            "gallery_urls": gallery_json,
            "stl_main_url": file_url,
            "stl_extra_urls": stl_extra_json,
            "zip_url": zip_url,
            "format": fmt,
            "user_id": user_id,
        },
    )
    if dialect == "postgresql":
        new_id = _row_to_dict(row.fetchone())["id"]
    else:
        new_id = db.session.execute(text("SELECT last_insert_rowid() AS id")).scalar()

    db.session.commit()

    # ✅ Trigger printability analysis (only for local files)
    # ⚠️ CRITICAL: Never block upload, even if analysis fails
    if file_url:  # Only attempt if we have a file URL
        try:
            stl_path = _resolve_stl_filesystem_path(file_url)
            
            if not stl_path:
                # Expected for Cloudinary URLs (though shouldn't happen after force_local fix)
                current_app.logger.debug(
                    f"⏭️ Skipping analysis for item {new_id}: "
                    f"file_url={file_url[:80]} (no local path - likely Cloudinary)"
                )
            elif not os.path.isfile(stl_path):
                # File path resolved but doesn't exist
                current_app.logger.warning(
                    f"⚠️ Cannot analyze item {new_id}: "
                    f"file not found at {stl_path}"
                )
            else:
                # File exists locally - proceed with analysis
                from utils.stl_analyzer import analyze_stl
                
                current_app.logger.debug(f"🔍 Analyzing STL for item {new_id}: {stl_path}")
                analysis = analyze_stl(stl_path)
                
                # Check if analysis succeeded
                if analysis.get("error"):
                    current_app.logger.warning(
                        f"⚠️ STL analysis had errors for item {new_id}: {analysis.get('error')}"
                    )
                
                # Update item with analysis results (even if partial)
                db.session.execute(
                    text(f"""
                        UPDATE {ITEMS_TBL}
                        SET printability_json = :json,
                            proof_score = :score,
                            analyzed_at = :at
                        WHERE id = :id
                    """),
                    {
                        "json": json.dumps(analysis),
                        "score": analysis.get("proof_score"),
                        "at": datetime.utcnow(),
                        "id": new_id
                    }
                )
                db.session.commit()
                
                current_app.logger.info(
                    f"✅ Analyzed STL {new_id}: proof_score={analysis.get('proof_score')}, "
                    f"triangles={analysis.get('triangles', 0)}, "
                    f"warnings={len(analysis.get('warnings', []))}"
                )
                
        except ImportError as e:
            current_app.logger.error(f"❌ STL analyzer import failed for item {new_id}: {e}")
        except Exception as e:
            # Catch ANY error to prevent upload failure
            current_app.logger.exception(
                f"❌ STL analysis completely failed for item {new_id}: {type(e).__name__}: {e}"
            )
            # Continue without analysis - upload must succeed

    return jsonify({"ok": True, "id": int(new_id)})


@bp.get('/api/item/<int:item_id>/printability')
def api_printability(item_id):
    """
    GET /api/item/123/printability
    
    Returns cached analysis from DB if present.
    Otherwise analyzes STL file, saves to DB, returns fresh data.
    """
    # ⚠️ CRITICAL: Check if proof_score columns exist before querying
    if not _has_column(ITEMS_TBL, "proof_score"):
        resp = jsonify({
            "ok": False,
            "error": "migration_required",
            "detail": "Database migration needed: proof_score columns not found. Run migrate_proof_score.sql"
        })
        resp.headers["Cache-Control"] = "no-store"
        return resp, 409  # 409 Conflict - migration required
    
    try:
        # 1. Fetch item
        row = db.session.execute(
            text(f"SELECT stl_main_url, printability_json, proof_score, analyzed_at FROM {ITEMS_TBL} WHERE id = :id"),
            {"id": item_id}
        ).first()
        
        if not row:
            resp = jsonify({"ok": False, "error": "item_not_found"})
            resp.headers["Cache-Control"] = "no-store"
            return resp, 404
        
        stl_url, cached_json, cached_score, analyzed_at = row
        
        # 2. Return cached if exists
        if cached_json:
            # Parse JSON string (TEXT column) - handle both str and dict
            printability_dict = json.loads(cached_json) if isinstance(cached_json, str) else cached_json
            
            resp = jsonify({
                "ok": True,
                "item_id": item_id,
                "proof_score": cached_score,
                "printability": printability_dict,
                "analyzed_at": analyzed_at.isoformat() if analyzed_at else None
            })
            resp.headers["Cache-Control"] = "no-store"
            return resp
        
        # 3. No cached data - try to analyze
        if not stl_url:
            resp = jsonify({"ok": False, "error": "no_stl_file"})
            resp.headers["Cache-Control"] = "no-store"
            return resp, 404
        
        stl_path = _resolve_stl_filesystem_path(stl_url)
        if not stl_path:
            resp = jsonify({
                "ok": False,
                "error": "no_local_stl",
                "detail": "STL is on Cloudinary or missing"
            })
            resp.headers["Cache-Control"] = "no-store"
            return resp, 404
        
        from utils.stl_analyzer import analyze_stl
        analysis = analyze_stl(stl_path)
        
        # 4. Save to DB
        db.session.execute(
            text(f"""
                UPDATE {ITEMS_TBL}
                SET printability_json = :json,
                    proof_score = :score,
                    analyzed_at = :at
                WHERE id = :id
            """),
            {
                "json": json.dumps(analysis),
                "score": analysis.get("proof_score"),
                "at": datetime.utcnow(),
                "id": item_id
            }
        )
        db.session.commit()
        
        resp = jsonify({
            "ok": True,
            "item_id": item_id,
            "proof_score": analysis.get("proof_score"),
            "printability": analysis,
            "analyzed_at": datetime.utcnow().isoformat()
        })
        resp.headers["Cache-Control"] = "no-store"
        return resp
        
    except Exception as e:
        current_app.logger.error(f"Printability analysis failed: {e}")
        resp = jsonify({"ok": False, "error": "analysis_failed", "detail": str(e)})
        resp.headers["Cache-Control"] = "no-store"
        return resp, 500


@bp.get('/api/item/<int:item_id>/slice-hints')
def api_slice_hints(item_id):
    """
    GET /api/item/123/slice-hints
    
    Returns cached slice hints from DB if present.
    Otherwise generates from printability_json + proof_score, saves to DB, returns fresh data.
    NEVER crashes - returns empty dict if data missing.
    """
    try:
        # 1. Fetch item (graceful fallback if columns don't exist)
        has_slice_cols = _has_column(ITEMS_TBL, "slice_hints_json")
        
        if has_slice_cols:
            # Try to get cached slice hints
            row = db.session.execute(
                text(f"""
                    SELECT printability_json, proof_score, slice_hints_json, slice_hints_at 
                    FROM {ITEMS_TBL} 
                    WHERE id = :id
                """),
                {"id": item_id}
            ).first()
        else:
            # Fallback: only get printability_json and proof_score
            row = db.session.execute(
                text(f"""
                    SELECT printability_json, proof_score 
                    FROM {ITEMS_TBL} 
                    WHERE id = :id
                """),
                {"id": item_id}
            ).first()
        
        if not row:
            resp = jsonify({"ok": False, "error": "item_not_found"})
            resp.headers["Cache-Control"] = "no-store"
            return resp, 404
        
        # 2. Check if cached slice hints exist
        if has_slice_cols and len(row) >= 4:
            printability_json, proof_score, cached_hints, hints_at = row
            
            if cached_hints:
                # Parse JSON string (TEXT column)
                hints_dict = json.loads(cached_hints) if isinstance(cached_hints, str) else cached_hints
                
                resp = jsonify({
                    "ok": True,
                    "item_id": item_id,
                    "slice_hints": hints_dict,
                    "generated_at": hints_at.isoformat() if hints_at else None
                })
                resp.headers["Cache-Control"] = "no-store"
                return resp
        else:
            printability_json, proof_score = row[0], row[1]
            cached_hints = None
        
        # 3. Generate fresh slice hints
        from utils.slice_hints import generate_slice_hints
        
        # Parse printability_json (handle TEXT column)
        printability = None
        if printability_json:
            try:
                printability = json.loads(printability_json) if isinstance(printability_json, str) else printability_json
            except:
                printability = None
        
        # Generate hints (NEVER crashes - has internal defaults)
        hints = generate_slice_hints(printability, proof_score)
        
        # 4. Save to DB if columns exist
        if has_slice_cols:
            try:
                db.session.execute(
                    text(f"""
                        UPDATE {ITEMS_TBL}
                        SET slice_hints_json = :hints,
                            slice_hints_at = :at
                        WHERE id = :id
                    """),
                    {
                        "hints": json.dumps(hints),
                        "at": datetime.utcnow(),
                        "id": item_id
                    }
                )
                db.session.commit()
            except Exception as save_err:
                current_app.logger.warning(f"Failed to save slice hints for item {item_id}: {save_err}")
                db.session.rollback()
        
        # 5. Return generated hints
        resp = jsonify({
            "ok": True,
            "item_id": item_id,
            "slice_hints": hints,
            "generated_at": hints.get("generated_at")
        })
        resp.headers["Cache-Control"] = "no-store"
        return resp
        
    except Exception as e:
        current_app.logger.error(f"Slice hints generation failed for item {item_id}: {e}")
        # Graceful fallback - return empty hints
        resp = jsonify({
            "ok": True,
            "item_id": item_id,
            "slice_hints": {},
            "error": str(e)
        })
        resp.headers["Cache-Control"] = "no-store"
        return resp


@bp.get('/api/item/<int:item_id>/slice-hints/preset')
def api_slice_hints_preset(item_id):
    """
    GET /api/item/123/slice-hints/preset?target=cura|prusa&nozzle=0.4|0.6&quality=draft|normal|fine
    
    Downloads slicer preset file generated from slice hints.
    Supports Cura and PrusaSlicer formats.
    Optional profile params (nozzle, quality) adjust settings.
    """
    target = request.args.get('target', 'cura').lower()
    if target not in {'cura', 'prusa'}:
        return jsonify({"ok": False, "error": "Invalid target. Use 'cura' or 'prusa'"}), 400
    
    # Optional profile params (safe parsing)
    nozzle = request.args.get('nozzle', '0.4')
    quality = request.args.get('quality', 'normal').lower()
    
    try:
        # 1. Get or generate slice hints (reuse existing logic)
        has_slice_cols = _has_column(ITEMS_TBL, "slice_hints_json")
        
        if has_slice_cols:
            row = db.session.execute(
                text(f"""
                    SELECT title, printability_json, proof_score, slice_hints_json 
                    FROM {ITEMS_TBL} 
                    WHERE id = :id
                """),
                {"id": item_id}
            ).first()
        else:
            row = db.session.execute(
                text(f"""
                    SELECT title, printability_json, proof_score 
                    FROM {ITEMS_TBL} 
                    WHERE id = :id
                """),
                {"id": item_id}
            ).first()
        
        if not row:
            return jsonify({"ok": False, "error": "item_not_found"}), 404
        
        # Parse row
        if has_slice_cols and len(row) >= 4:
            title, printability_json, proof_score, cached_hints = row
        else:
            title, printability_json, proof_score = row[0], row[1], row[2]
            cached_hints = None
        
        # Get hints (cached or generate)
        hints = None
        if cached_hints:
            hints = json.loads(cached_hints) if isinstance(cached_hints, str) else cached_hints
        
        if not hints or not isinstance(hints, dict) or len(hints) == 0:
            # Generate fresh hints
            from utils.slice_hints import generate_slice_hints
            
            printability = None
            if printability_json:
                try:
                    printability = json.loads(printability_json) if isinstance(printability_json, str) else printability_json
                except:
                    printability = None
            
            hints = generate_slice_hints(printability, proof_score)
            
            # Save to DB if columns exist
            if has_slice_cols and hints:
                try:
                    db.session.execute(
                        text(f"""
                            UPDATE {ITEMS_TBL}
                            SET slice_hints_json = :hints,
                                slice_hints_at = :at
                            WHERE id = :id
                        """),
                        {
                            "hints": json.dumps(hints),
                            "at": datetime.utcnow(),
                            "id": item_id
                        }
                    )
                    db.session.commit()
                except Exception as save_err:
                    current_app.logger.warning(f"Failed to save slice hints during preset download: {save_err}")
                    db.session.rollback()
        
        # 2. Apply profile modifiers (nozzle, quality)
        modified_hints = _apply_profile_modifiers(hints, nozzle, quality)
        
        # 3. Build preset file content
        preset_content = _build_preset_content(modified_hints, target, title or f"item_{item_id}")
        
        # 4. Create response with download headers
        safe_title = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in (title or f"item_{item_id}"))[:50]
        
        if target == 'cura':
            filename = f"{safe_title}_cura.curaprofile"
        else:  # prusa
            filename = f"{safe_title}_prusa.prusapreset"
        
        resp = make_response(preset_content)
        resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        resp.headers['Cache-Control'] = 'no-store'
        return resp
        
    except Exception as e:
        current_app.logger.error(f"Preset download failed for item {item_id}: {e}")
        return jsonify({"ok": False, "error": "preset_generation_failed", "detail": str(e)}), 500


def _apply_profile_modifiers(hints, nozzle_str, quality):
    """
    Apply profile modifiers (nozzle size, quality) to slice hints.
    Returns a modified copy of hints dict.
    
    Args:
        hints: Original hints dict
        nozzle_str: "0.4" or "0.6" (or other)
        quality: "draft", "normal", or "fine"
    
    Returns:
        Modified hints dict
    """
    # Work on a copy to avoid mutating original
    modified = hints.copy()
    
    # Parse nozzle safely
    try:
        nozzle = float(nozzle_str)
    except (ValueError, TypeError):
        nozzle = 0.4
    
    # Get base layer height
    layer_height = modified.get('layer_height', 0.2)
    estimated_time = modified.get('estimated_time_hours', 0)
    
    # Apply quality modifier
    if quality == 'fine':
        layer_height *= 0.8
    elif quality == 'draft':
        layer_height *= 1.2
    # 'normal' -> no change
    
    # Apply nozzle modifier
    if abs(nozzle - 0.6) < 0.01:  # nozzle == 0.6
        layer_height = min(layer_height + 0.04, 0.32)
        estimated_time *= 0.85
    
    # Clamp layer height
    layer_height = max(0.12, min(layer_height, 0.32))
    
    # Update modified hints
    modified['layer_height'] = round(layer_height, 2)
    modified['estimated_time_hours'] = round(estimated_time, 1)
    
    return modified


def _build_preset_content(hints, target, title):
    """
    Build slicer preset file content from slice hints.
    
    Args:
        hints: Dict with layer_height, infill_percent, supports, material, etc.
        target: 'cura' or 'prusa'
        title: Item title for comments
    
    Returns:
        String with preset file content
    """
    # Sanitize title for safe inclusion in comments
    safe_title = title.replace('\n', ' ').replace('\r', ' ')[:100]
    
    layer_height = hints.get('layer_height', 0.2)
    infill = hints.get('infill_percent', 15)
    supports = hints.get('supports', 'none')
    material = hints.get('material', 'PLA')
    
    if target == 'cura':
        # Cura preset format (INI-like)
        lines = [
            f"# Proofly Auto-Generated Preset for {safe_title}",
            f"# Material: {material}",
            f"# Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "[general]",
            "version = 4",
            "name = Proofly Auto",
            "definition = fdmprinter",
            "",
            "[metadata]",
            f"quality_type = proofly",
            f"material = {material.lower()}",
            "",
            "[values]",
            f"layer_height = {layer_height}",
            f"infill_sparse_density = {infill}",
        ]
        
        # Support settings
        if supports == 'none':
            lines.append("support_enable = False")
        elif supports == 'buildplate':
            lines.append("support_enable = True")
            lines.append("support_type = buildplate")
        else:  # everywhere
            lines.append("support_enable = True")
            lines.append("support_type = everywhere")
        
        return "\n".join(lines)
    
    else:  # prusa
        # PrusaSlicer preset format (INI sections)
        lines = [
            f"# Proofly Auto-Generated Preset for {safe_title}",
            f"# Material: {material}",
            f"# Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "[print:Proofly Auto]",
            f"layer_height = {layer_height}",
            f"fill_density = {infill}%",
        ]
        
        # Support settings
        if supports == 'none':
            lines.append("support_material = 0")
        elif supports == 'buildplate':
            lines.append("support_material = 1")
            lines.append("support_material_buildplate_only = 1")
        else:  # everywhere
            lines.append("support_material = 1")
            lines.append("support_material_buildplate_only = 0")
        
        return "\n".join(lines)


# ✅ Сумісність з фронтом: /api/market/upload (BASE="/api/market" у api.js)
@bp.post("/api/market/upload")
def api_upload_compat():
    return api_upload()


def _fetch_item_with_author(item_id: int) -> Optional[Dict[str, Any]]:
    sql_primary = f"""
      SELECT i.*,
             COALESCE(i.stl_main_url, '') AS url,
             u.name   AS author_name,
             u.email  AS author_email,
             u.id     AS author_id,
             COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar,
             COALESCE(u.bio, '3D-дизайнер') AS author_bio
      FROM {ITEMS_TBL} i
      LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
      WHERE i.id = :id
    """
    try:
        row = db.session.execute(text(sql_primary), {"id": item_id}).fetchone()
    except sa_exc.ProgrammingError:
        db.session.rollback()
        row = db.session.execute(
            text(
                f"""
          SELECT i.*,
                 u.name AS author_name,
                 u.email AS author_email,
                 u.id AS author_id
          FROM {ITEMS_TBL} i
          LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
          WHERE i.id = :id
        """
            ),
            {"id": item_id},
        ).fetchone()

    if not row:
        return None

    d = _row_to_dict(row)
    d.setdefault("author_avatar", "/static/img/user.jpg")
    d.setdefault("author_bio", "3D-дизайнер")

    # Safe parsing of photos/gallery with _safe_json_list
    images: list = []
    stl_files: list = []
    
    ph = d.get("photos")
    if isinstance(ph, dict):
        images = [s for s in (ph.get("images") or []) if s]
        stl_files = [s for s in (ph.get("stl") or []) if s]
    elif isinstance(ph, list):
        images = [s for s in ph if s]
    else:
        # Try to parse as JSON
        data = _safe_json_list(ph)
        if data:
            images = [s for s in data if s]

    if not images:
        g_list = _safe_json_list(d.get("gallery_urls"))
        images = [s for s in g_list if s]
    if not stl_files:
        s_list = _safe_json_list(d.get("stl_extra_urls"))
        stl_files = [s for s in s_list if s]

    if not d.get("cover"):
        d["cover"] = d.get("cover_url") or d.get("cover") or (images[0] if images else None)
    if not d.get("url"):
        d["url"] = d.get("stl_main_url") or d.get("file_url") or (stl_files[0] if stl_files else None)

    d["photos"] = images[:5]
    d["stl_files"] = stl_files[:5]

    c = _normalize_cover_url(d.get("cover") or d.get("cover_url"))
    d["cover"] = c
    d["cover_url"] = c

    # ensure gallery_urls normalized for detail response
    raw_gallery = d.get("gallery_urls") or d.get("photos")
    gallery_list = _safe_json_list(raw_gallery)
    
    normalized_gallery = []
    for g in gallery_list:
        try:
            url = g.get("url") if isinstance(g, dict) else str(g)
        except Exception:
            url = None
        if not url:
            continue
        url_norm = _normalize_cover_url(url)
        if url_norm:
            normalized_gallery.append(url_norm)
    d["gallery_urls"] = normalized_gallery

    return d


@bp.record_once
def _mount_persistent_uploads(setup_state):
    app = setup_state.app
    persist_root = app.config.get("UPLOADS_ROOT") or os.environ.get("UPLOADS_ROOT")
    if not persist_root:
        return
    try:
        os.makedirs(persist_root, exist_ok=True)
        static_root = os.path.join(app.root_path, "static")
        os.makedirs(static_root, exist_ok=True)
        link_path = os.path.join(static_root, "market_uploads")

        if os.path.islink(link_path):
            return

        if os.path.isdir(link_path):
            for name in os.listdir(link_path):
                src = os.path.join(link_path, name)
                dst = os.path.join(persist_root, name)
                if not os.path.exists(dst):
                    shutil.move(src, dst)
            os.rmdir(link_path)

        if not os.path.exists(link_path):
            os.symlink(persist_root, link_path, target_is_directory=True)
    except Exception as e:
        app.logger.error("UPLOADS_ROOT mount failed: %r", e)


@bp.before_app_request
def _static_market_uploads_fallback():
    p = request.path
    if request.method != "GET":
        return

    if p.startswith("/static/market_uploads/media/"):
        fname = p.split("/static/market_uploads/media/", 1)[1]
        return redirect("/media/" + fname, code=302)

    if not p.startswith("/static/market_uploads/"):
        return

    fs_path = os.path.join(current_app.root_path, p.lstrip("/"))
    if os.path.exists(fs_path):
        return

    lower = p.lower()
    if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return current_app.send_static_file("img/placeholder_stl.jpg")

    if lower.endswith((".stl", ".obj", ".glb", ".gltf", ".zip", ".ply")):
        abort(404)


@bp.get("/media/<path:fname>")
@bp.get("/market/media/<path:fname>")
@bp.get("/static/market_uploads/media/<path:fname>")
def market_media(fname: str):
    """
    Serve media files by checking:
      1) configured UPLOADS_ROOT (/media/<...>)  ✅ (now uses _uploads_root())
      2) legacy static/market_uploads
      3) app.static
    """
    safe = os.path.normpath(fname).lstrip(os.sep)

    uploads_root = _uploads_root()
    abs_path = os.path.join(uploads_root, safe)
    if os.path.isfile(abs_path):
        base_dir = uploads_root
        safe_to_serve = safe
    else:
        legacy_root = os.path.join(current_app.root_path, "static", "market_uploads")
        legacy_path = os.path.join(legacy_root, safe)
        if os.path.isfile(legacy_path):
            base_dir = legacy_root
            safe_to_serve = safe
        else:
            static_path = os.path.join(current_app.root_path, "static", safe)
            if os.path.isfile(static_path):
                base_dir = os.path.join(current_app.root_path, "static")
                safe_to_serve = safe
            else:
                low = safe.lower()
                if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    return current_app.send_static_file("img/placeholder_stl.jpg")
                abort(404)

    mime = None
    low = safe_to_serve.lower()
    if low.endswith(".stl"):
        mime = "model/stl"
    elif low.endswith(".obj"):
        mime = "text/plain"
    elif low.endswith(".glb"):
        mime = "model/gltf-binary"
    elif low.endswith(".gltf"):
        mime = "model/gltf+json"
    elif low.endswith(".zip"):
        mime = "application/zip"
    elif low.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif low.endswith(".png"):
        mime = "image/png"
    elif low.endswith(".webp"):
        mime = "image/webp"

    return send_from_directory(base_dir, safe_to_serve, mimetype=mime)

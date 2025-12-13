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
from models import db, MarketItem, MarketFavorite, MarketReview
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

# Default fallback upload dir (legacy static)
LEGACY_STATIC_UPLOADS = os.path.join("static", "market_uploads")
os.makedirs(LEGACY_STATIC_UPLOADS, exist_ok=True)

ALLOWED_MODEL_EXT = {".stl", ".obj", ".ply", ".gltf", ".glb"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_ARCHIVE_EXT = {".zip"}

COVER_PLACEHOLDER = "/static/img/placeholder_stl.jpg"


def _row_to_dict(row) -> Dict[str, Any]:
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)


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


def _normalize_free(value: Optional[str]) -> str:
    v = (value or "all").lower()
    return v if v in ("all", "free", "paid") else "all"


def _normalize_sort(value: Optional[str]) -> str:
    v = (value or "new").lower()
    return v if v in ("new", "price_asc", "price_desc", "downloads") else "new"


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
    This function keeps its signature unchanged.
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in allowed_ext:
        return None

    base_name = secure_filename(os.path.basename(file_storage.filename)) or ("file" + ext)
    unique_name = f"{os.path.splitext(base_name)[0]}_{uuid.uuid4().hex}{ext}"

    # Try cloudinary first if configured
    if _CLOUDINARY_READY:
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
    # Get cover from cover_url or cover field
    raw_cover = it.get("cover_url") or it.get("cover") or ""
    
    # Parse gallery_urls (may be JSON string or list) - SAFE parsing
    raw_gallery = it.get("gallery_urls") or it.get("photos")
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
    is_published = it.get("is_published")
    if is_published is None:
        is_published = True  # default for legacy items
    else:
        is_published = bool(is_published)
    
    published_at = it.get("published_at")
    status = "published" if is_published else "draft"
    
    return {
        "id": it.get("id"),
        "title": it.get("title"),
        "price": it.get("price"),
        "tags": it.get("tags"),
        "cover_url": cover_url,  # ✅ Always normalized, never "no image"
        "gallery_urls": normalized_gallery,
        "rating": it.get("rating", 0),
        "downloads": it.get("downloads", 0),
        "url": it.get("url") or it.get("stl_main_url"),
        "format": it.get("format"),
        "user_id": it.get("user_id"),
        "created_at": it.get("created_at"),
        "price_cents": it.get("price_cents") or (int(it.get("price", 0) * 100) if it.get("price") else 0),
        "is_free": it.get("is_free") or (it.get("price", 0) == 0),
        "is_published": is_published,
        "published_at": published_at,
        "status": status,
    }


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
    return render_template("market/index.html")


@bp.get("/market/mine")
def page_market_mine():
    return render_template("market_mine.html")


@bp.get("/market/my-ads")
def page_market_my_ads():
    return render_template("market/my-ads.html")


@bp.get("/market/my")
def page_market_my():
    return render_template("market/my.html")


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
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        abort(401)

    it = _fetch_item_with_author(item_id)
    if not it:
        abort(404)

    if _parse_int(it.get("user_id"), 0) != uid:
        abort(403)

    return render_template("market/edit_model.html", item=it)


@bp.get("/api/items")
def api_items():
    try:
        raw_q = request.args.get("q") or ""
        q = raw_q.strip().lower()

        free = _normalize_free(request.args.get("free"))
        sort = _normalize_sort(request.args.get("sort"))
        page = max(1, _parse_int(request.args.get("page"), 1))
        per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))

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
        if q:
            where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
            params["q"] = f"%{q}%"
        if free == "free":
            where.append("price = 0")
        elif free == "paid":
            where.append("price > 0")
        
        # ✅ Filter only published items in public market
        try:
            # Check if is_published column exists
            db.session.execute(text(f"SELECT is_published FROM {ITEMS_TBL} LIMIT 1")).fetchone()
            where.append("(is_published = 1 OR is_published IS NULL)")
        except Exception:
            db.session.rollback()
            # Column doesn't exist yet, skip filter
            pass
        
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        if sort == "price_asc":
            order_sql = "ORDER BY price ASC, created_at DESC"
        elif sort == "price_desc":
            order_sql = "ORDER BY price DESC, created_at DESC"
        elif sort == "downloads":
            order_sql = "ORDER BY downloads DESC, created_at DESC"
        else:
            order_sql = "ORDER BY created_at DESC, id DESC"

        offset = (page - 1) * per_page

        # ⚠️ HOTFIX: Try full query with is_published inside try block, fallback if column missing
        try:
            # Build SQL with is_published columns - ALL inside try
            sql_with_publish = f"""
                SELECT id, title, price, tags,
                       COALESCE(cover_url, '') AS cover,
                       COALESCE(gallery_urls, '[]') AS gallery_urls,
                       COALESCE(rating, 0) AS rating,
                       COALESCE(downloads, 0) AS downloads,
                       {url_expr} AS url,
                       format, user_id, created_at,
                       is_published, published_at
                FROM {ITEMS_TBL}
                {where_sql}
                {order_sql}
                LIMIT :limit OFFSET :offset
            """
            
            rows = db.session.execute(text(sql_with_publish), {**params, "limit": per_page, "offset": offset}).fetchall()
            items = [_row_to_dict(r) for r in rows]
            total = db.session.execute(text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_sql}"), params).scalar() or 0
            
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
                           {url_expr} AS url,
                           format, user_id, created_at
                    FROM {ITEMS_TBL}
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """
                
                try:
                    rows = db.session.execute(text(sql_fallback), {**params, "limit": per_page, "offset": offset}).fetchall()
                    items = [_row_to_dict(r) for r in rows]
                    total = db.session.execute(text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_sql}"), params).scalar() or 0
                except sa_exc.ProgrammingError:
                    # Last resort: legacy schema with file_url instead of stl_main_url
                    db.session.rollback()
                    sql_legacy = f"""
                        SELECT id, title, price, tags,
                               COALESCE(cover, '') AS cover,
                               COALESCE(gallery_urls, '[]') AS gallery_urls,
                               COALESCE(file_url,'') AS url,
                               user_id, created_at
                        FROM {ITEMS_TBL}
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
                        items.append(d)
                    total = db.session.execute(text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_sql}"), params).scalar() or 0
            else:
                # Other error - re-raise
                raise

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

    except Exception as e:
        # ✅ Bulletproof: log full traceback to Railway, return controlled response
        current_app.logger.exception("🔥 api_items FAILED: %s", e)
        
        # Parse request params for fallback response
        try:
            page = max(1, _parse_int(request.args.get("page"), 1))
            per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))
            sort = _normalize_sort(request.args.get("sort"))
        except Exception:
            page, per_page, sort = 1, 24, "new"
        
        # Return 200 with empty list - never crash the market
        return jsonify({
            "ok": False,
            "items": [],
            "page": page,
            "per_page": per_page,
            "pages": 0,
            "total": 0,
            "sort": sort,
            "error": "api_items_failed"
        }), 200


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
                           COALESCE(cover, '') AS cover,
                           COALESCE(gallery_urls, '[]') AS gallery_urls,
                           COALESCE(file_url,'') AS url,
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
                    SET is_published = 1,
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
                    SET is_published = 0,
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
    return jsonify({"ok": True, "id": int(new_id)})


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

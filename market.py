import os
import math
import json
import shutil
import uuid
from typing import Any, Dict, Optional

from flask import Blueprint, render_template, jsonify, request, session, current_app, send_from_directory, abort, redirect
from sqlalchemy import text
from sqlalchemy import exc as sa_exc
from werkzeug.utils import secure_filename

# ✅ Cloudinary (хмарне зберігання)
try:
    import cloudinary
    import cloudinary.uploader
    _CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
    if _CLOUDINARY_URL:
        cloudinary.config(cloudinary_url=_CLOUDINARY_URL)
    _CLOUDINARY_READY = bool(_CLOUDINARY_URL)
except Exception:
    _CLOUDINARY_READY = False

# ✅ бази та моделі
from models import db, MarketItem
from db import User

bp = Blueprint("market", __name__)

ITEMS_TBL = getattr(MarketItem, "__tablename__", "items") or "items"
USERS_TBL = getattr(User, "__tablename__", "users") or "users"

UPLOAD_DIR = os.path.join("static", "market_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

def _normalize_free(value: Optional[str]) -> str:
    v = (value or "all").lower()
    return v if v in ("all", "free", "paid") else "all"

def _normalize_sort(value: Optional[str]) -> str:
    v = (value or "new").lower()
    return v if v in ("new", "price_asc", "price_desc", "downloads") else "new"

def _local_media_exists(media_url: str) -> bool:
    if not media_url or not media_url.startswith("/media/"):
        return False
    rel = media_url[len("/media/"):].lstrip("/")
    abs_path = os.path.join(current_app.root_path, "static", "market_uploads", rel)
    return os.path.isfile(abs_path)

def _normalize_cover_url(url: Optional[str]) -> str:
    """Повертає валідний URL (Cloudinary, /media або плейсхолдер)."""
    u = (url or "").strip()
    if not u:
        return COVER_PLACEHOLDER
    if u.startswith(("http://", "https://", "data:")):
        return u
    if u.startswith("/media/") and _local_media_exists(u):
        return u
    return COVER_PLACEHOLDER

def _save_upload(file_storage, subdir: str, allowed_ext: set) -> Optional[str]:
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in allowed_ext:
        return None

    base_name = secure_filename(os.path.basename(file_storage.filename)) or ("file" + ext)
    unique_name = f"{os.path.splitext(base_name)[0]}_{uuid.uuid4().hex}{ext}"

    if _CLOUDINARY_READY:
        try:
            folder = f"proofly/market/{subdir}".replace("\\", "/")
            if ext in ALLOWED_IMAGE_EXT:
                res = cloudinary.uploader.upload(
                    file_storage, folder=folder,
                    public_id=os.path.splitext(unique_name)[0]
                )
            else:
                res = cloudinary.uploader.upload(
                    file_storage, folder=folder,
                    resource_type="raw",
                    public_id=os.path.splitext(unique_name)[0]
                )
            url = res.get("secure_url") or res.get("url")
            if url:
                return url
        except Exception as _e:
            try:
                current_app.logger.warning(f"Cloudinary upload failed, fallback to local: {type(_e).__name__}: {_e}")
            except Exception:
                pass

    static_root = os.path.join(current_app.root_path, "static")
    folder = os.path.join(static_root, "market_uploads", subdir)
    os.makedirs(folder, exist_ok=True)

    name = unique_name
    dst = os.path.join(folder, name)
    file_storage.save(dst)

    rel_inside_market = os.path.join(subdir, name).replace("\\", "/")
    return f"/media/{rel_inside_market}"

def json_dumps_safe(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "[]"


@bp.get("/market")
def page_market():
    return render_template("market.html")

@bp.get("/market/mine")
def page_market_mine():
    return render_template("market_mine.html")

@bp.get("/item/<int:item_id>")
def page_item(item_id: int):
    it = _fetch_item_with_author(item_id)
    if not it:
        return render_template("item.html", item=None), 404
    return render_template("item.html", item=it)

@bp.get("/upload")
def page_upload():
    return render_template("upload.html")

@bp.get("/edit/<int:item_id>")
def page_edit_item(item_id: int):
    return render_template("edit.html")


@bp.get("/api/items")
def api_items():
    q = (request.args.get("q") or "").strip().lower()
    free = _normalize_free(request.args.get("free"))
    sort = _normalize_sort(request.args.get("sort"))
    page = max(1, _parse_int(request.args.get("page"), 1))
    per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))

    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
        tags_expr  = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
        cover_expr = "COALESCE(cover_url, '')"
        url_expr   = "stl_main_url"
    else:
        title_expr = "LOWER(COALESCE(title, ''))"
        tags_expr  = "LOWER(COALESCE(tags,  ''))"
        cover_expr = "COALESCE(cover_url, '')"
        url_expr   = "stl_main_url"

    where, params = [], {}
    if q:
        where.append(f"({title_expr} LIKE :q OR {tags_expr} LIKE :q)")
        params["q"] = f"%{q}%"
    if free == "free":
        where.append("price = 0")
    elif free == "paid":
        where.append("price > 0")
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

    total = db.session.execute(
        text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_sql}"), params
    ).scalar() or 0

    sql = f"""
        SELECT id, title, price, tags,
               COALESCE(cover_url, '') AS cover,
               COALESCE(rating, 0) AS rating,
               COALESCE(downloads, 0) AS downloads,
               {url_expr} AS url,
               format, user_id, created_at
        FROM {ITEMS_TBL}
        {where_sql}
        {order_sql}
        LIMIT :limit OFFSET :offset
    """

    rows = db.session.execute(
        text(sql), {**params, "limit": per_page, "offset": offset}
    ).fetchall()
    items = [_row_to_dict(r) for r in rows]

    # 🔧 нормалізуємо обкладинки
    for it in items:
        c = _normalize_cover_url(it.get("cover") or it.get("cover_url"))
        it["cover"] = c
        it["cover_url"] = c

    return jsonify({
        "items": items,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if per_page else 1,
        "total": total
    })


@bp.get("/api/my/items")
def api_my_items():
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"error": "unauthorized"}), 401

    page = max(1, _parse_int(request.args.get("page"), 1))
    per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))
    offset = (page - 1) * per_page

    sql = f"""
        SELECT id, title, price, tags,
               COALESCE(cover_url, '') AS cover,
               COALESCE(rating, 0) AS rating,
               COALESCE(downloads, 0) AS downloads,
               stl_main_url AS url,
               format, user_id, created_at
        FROM {ITEMS_TBL}
        WHERE user_id = :uid
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = db.session.execute(
        text(sql),
        {"uid": uid, "limit": per_page, "offset": offset}
    ).fetchall()
    items = [_row_to_dict(r) for r in rows]
    total = db.session.execute(
        text(f"SELECT COUNT(*) FROM {ITEMS_TBL} WHERE user_id = :uid"),
        {"uid": uid}
    ).scalar() or 0

    for it in items:
        c = _normalize_cover_url(it.get("cover") or it.get("cover_url"))
        it["cover"] = c
        it["cover_url"] = c

    return jsonify({
        "items": items,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if per_page else 1,
        "total": total
    })


@bp.get("/api/item/<int:item_id>")
def api_item(item_id: int):
    it = _fetch_item_with_author(item_id)
    if not it:
        return jsonify({"error": "not_found"}), 404
    return jsonify(it)


@bp.post("/api/item/<int:item_id>/download")
def api_item_download(item_id: int):
    dialect = db.session.get_bind().dialect.name
    try:
        if dialect == "postgresql":
            db.session.execute(
                text(f"""UPDATE {ITEMS_TBL}
                         SET downloads = COALESCE(downloads,0) + 1,
                             updated_at = NOW()
                         WHERE id = :id"""),
                {"id": item_id}
            )
        else:
            db.session.execute(
                text(f"""UPDATE {ITEMS_TBL}
                         SET downloads = COALESCE(downloads,0) + 1,
                             updated_at = CURRENT_TIMESTAMP
                         WHERE id = :id"""),
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


# інші функції (upload, _fetch_item_with_author, static, media) без змін…

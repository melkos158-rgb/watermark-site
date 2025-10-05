# market.py — STL Market (Blueprint)
# Маршрути:
#   GET  /market                  — каталог (пошук/фільтри/сортування/пагінація)
#   GET  /item/<id>               — сторінка моделі
#   GET  /upload                  — сторінка завантаження (форма)
#   API:
#   GET  /api/items               — список (q, free, sort, page, per_page)
#   GET  /api/item/<id>           — деталі моделі + автор
#   POST /api/upload              — додати модель (мок; у БД items)
#   POST /api/item/<id>/download  — інкремент лічильника завантажень

import os
import math
import json
from typing import Any, Dict, Optional

from flask import Blueprint, render_template, jsonify, request, session
from sqlalchemy import text
from werkzeug.utils import secure_filename

from db import db, User

bp = Blueprint("market", __name__)

ITEMS_TBL = "items"
USERS_TBL = getattr(User, "__tablename__", "users") or "users"

# куди класти завантажені файли
UPLOAD_DIR = os.path.join("static", "market_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_MODEL_EXT = {".stl", ".obj", ".ply", ".gltf", ".glb"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


# ----------------------- helpers -----------------------

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

def _save_upload(file_storage, subdir: str, allowed_ext: set) -> Optional[str]:
    """
    Зберігає файл у static/market_uploads/<subdir>/... і повертає
    шлях ВІДНОСНО static/ (щоб віддавати через /static/...).
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None
    fname = file_storage.filename
    ext = os.path.splitext(fname)[1].lower()
    if ext not in allowed_ext:
        return None
    safe = secure_filename(os.path.basename(fname))
    folder = os.path.join(UPLOAD_DIR, subdir)
    os.makedirs(folder, exist_ok=True)
    final_name = f"{safe}"
    abs_path = os.path.join(folder, final_name)
    # якщо імʼя вже існує — додаємо суфікс
    base, e = os.path.splitext(final_name)
    i = 1
    while os.path.exists(abs_path):
        final_name = f"{base}_{i}{e}"
        abs_path = os.path.join(folder, final_name)
        i += 1
    file_storage.save(abs_path)
    # повертаємо шлях відносно static/
    rel_from_static = os.path.relpath(abs_path, "static").replace("\\", "/")
    return f"/static/{rel_from_static}"

def json_dumps_safe(obj) -> str:
    """Повертає JSON-строку для вставки у CAST(:photos AS JSON)."""
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "[]"


# ----------------------- pages -------------------------

@bp.get("/market")
def page_market():
    return render_template("market.html")

@bp.get("/item/<int:item_id>")
def page_item(item_id: int):
    it = _fetch_item_with_author(item_id)
    if not it:
        return render_template("item.html", item=None), 404
    return render_template("item.html", item=it)

@bp.get("/upload")
def page_upload():
    return render_template("upload.html")


# ------------------------- API -------------------------

@bp.get("/api/items")
def api_items():
    """
    q: пошук по title і tags
    free: all | free | paid
    sort: new | price_asc | price_desc | downloads
    page, per_page: пагінація
    """
    q = (request.args.get("q") or "").strip().lower()
    free = _normalize_free(request.args.get("free"))
    sort = _normalize_sort(request.args.get("sort"))
    page = max(1, _parse_int(request.args.get("page"), 1))
    per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))

    where = []
    params = {}
    if q:
        where.append("(LOWER(title) LIKE :q OR LOWER(tags) LIKE :q)")
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
        text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_sql}"),
        params
    ).scalar() or 0

    rows = db.session.execute(
        text(f"""
            SELECT id, title, price, tags, cover, rating, downloads,
                   file_url AS url, format, user_id, created_at
            FROM {ITEMS_TBL}
            {where_sql}
            {order_sql}
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": per_page, "offset": offset}
    ).fetchall()

    items = [_row_to_dict(r) for r in rows]
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
    upd = db.session.execute(
        text(f"UPDATE {ITEMS_TBL} SET downloads = downloads + 1, updated_at = NOW() WHERE id = :id"),
        {"id": item_id}
    )
    db.session.commit()
    if upd.rowcount == 0:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True})

@bp.post("/api/upload")
def api_upload():
    """
    Приймає і JSON, і multipart/form-data (FormData).
    Поля:
      title, price, tags(list|comma), desc, format, url(file_url) або stl_file
      cover_url або cover_file
      user_id (необовʼязково; беремо із session.user_id)
    """
    # ---- 1) прочитати дані (JSON або форма) ----
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        form = request.form
        files = request.files
        title = (form.get("title") or "").strip()
        price = _parse_int(form.get("price"), 0)
        desc = (form.get("desc") or "").strip()
        fmt = (form.get("format") or "stl").strip().lower()
        # tags: або json-рядок, або "a,b,c"
        raw_tags = form.get("tags") or ""
        try:
            tags_val = json.loads(raw_tags) if raw_tags and raw_tags.strip().startswith("[") else raw_tags
        except Exception:
            tags_val = raw_tags

        # Модель: або URL, або файл
        file_url = (form.get("stl_url") or form.get("url") or "").strip()
        if not file_url and "stl_file" in files:
            uid = _parse_int(session.get("user_id"), 0) or 0
            saved = _save_upload(files["stl_file"], f"user_{uid}/models", ALLOWED_MODEL_EXT)
            if saved:
                file_url = saved

        # Обкладинка: або URL, або файл
        cover = (form.get("cover_url") or "").strip()
        if not cover and "cover_file" in files:
            uid = _parse_int(session.get("user_id"), 0) or 0
            saved = _save_upload(files["cover_file"], f"user_{uid}/covers", ALLOWED_IMAGE_EXT)
            if saved:
                cover = saved

        # user_id
        user_id = _parse_int(form.get("user_id"), 0) or _parse_int(session.get("user_id"), 0)

    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        price = _parse_int(data.get("price"), 0)
        desc = (data.get("desc") or "").strip()
        fmt = (data.get("format") or "stl").strip().lower()
        file_url = (data.get("url") or data.get("file_url") or "").strip()
        cover = (data.get("cover") or "").strip()
        tags_val = data.get("tags") or ""
        user_id = _parse_int(data.get("user_id"), 0) or _parse_int(session.get("user_id"), 0)

    # ---- 2) нормалізувати теги ----
    if isinstance(tags_val, list):
        tags_str = ",".join([str(t).strip() for t in tags_val if str(t).strip()])
    else:
        tags_str = str(tags_val or "")

    # ---- 3) валідація мінімальних полів ----
    if not title or not file_url or not user_id:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    photos_json = json_dumps_safe([])

    # ---- 4) вставка в БД ----
    row = db.session.execute(
        text(f"""
            INSERT INTO {ITEMS_TBL}
              (title, desc, price, tags, cover, photos, file_url, format,
               downloads, user_id, created_at, updated_at)
            VALUES
              (:title, :desc, :price, :tags, :cover, CAST(:photos AS JSON),
               :file_url, :format, 0, :user_id, NOW(), NOW())
            RETURNING id
        """),
        {
            "title": title,
            "desc": desc,
            "price": price,
            "tags": tags_str,
            "cover": cover,
            "photos": photos_json,
            "file_url": file_url,
            "format": fmt,
            "user_id": user_id,
        }
    ).fetchone()

    new_id = _row_to_dict(row)["id"]
    db.session.commit()
    return jsonify({"ok": True, "id": new_id})


# -------------------- internal fetchers --------------------

def _fetch_item_with_author(item_id: int) -> Optional[Dict[str, Any]]:
    row = db.session.execute(
        text(f"""
          SELECT i.*, 
                 i.file_url AS url,
                 u.name   AS author_name,
                 u.email  AS author_email,
                 u.id     AS author_id,
                 COALESCE(u.avatar_url, '/static/avatars/default.jpg') AS author_avatar,
                 COALESCE(u.bio, '3D-дизайнер') AS author_bio
          FROM {ITEMS_TBL} i
          LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
          WHERE i.id = :id
        """),
        {"id": item_id}
    ).fetchone()
    return _row_to_dict(row) if row else None

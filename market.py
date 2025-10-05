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
from datetime import datetime
from typing import Any, Dict, Optional

from flask import Blueprint, render_template, jsonify, request, session
from sqlalchemy import text
from werkzeug.utils import secure_filename

from db import db, User

bp = Blueprint("market", __name__)

ITEMS_TBL = "items"
USERS_TBL = getattr(User, "__tablename__", "users") or "users"

# ===== uploads =====
UPLOAD_MODELS_DIR = os.path.join("static", "uploads", "models")
UPLOAD_COVERS_DIR = os.path.join("static", "uploads", "covers")
os.makedirs(UPLOAD_MODELS_DIR, exist_ok=True)
os.makedirs(UPLOAD_COVERS_DIR, exist_ok=True)

ALLOWED_MODEL_EXT = {"stl", "obj", "ply", "gltf", "glb"}
ALLOWED_IMG_EXT = {"jpg", "jpeg", "png", "webp"}

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

def _save_file(file_storage, folder: str, allowed_ext: set) -> Optional[str]:
    """Зберігає файл у static/uploads/... Повертає відносний URL або None."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in allowed_ext:
        return None
    fname = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(file_storage.filename)}"
    rel_path = os.path.join("static", "uploads", folder, fname).replace("\\", "/")
    abs_path = os.path.join(os.getcwd(), rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    file_storage.save(abs_path)
    return "/" + rel_path  # URL з косою рискою

# ----------------------- pages -------------------------

@bp.get("/market")
def page_market():
    # сам список підтягнеться на клієнті через /api/items
    return render_template("market.html")

@bp.get("/item/<int:item_id>")
def page_item(item_id: int):
    """Рендеримо картку з наповненим item, щоб працював і без XHR."""
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

    # фільтри
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

    # сортування
    if sort == "price_asc":
        order_sql = "ORDER BY price ASC, created_at DESC"
    elif sort == "price_desc":
        order_sql = "ORDER BY price DESC, created_at DESC"
    elif sort == "downloads":
        order_sql = "ORDER BY downloads DESC, created_at DESC"
    else:  # new
        order_sql = "ORDER BY created_at DESC, id DESC"

    # ліміт/офсет
    offset = (page - 1) * per_page

    # загальна кількість
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
    """Збільшує лічильник завантажень (можеш викликати перед редіректом на файл)."""
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
    Додає нову модель у таблицю items.

    Підтримує ДВА варіанти вводу:
    - JSON:  title, price, url(file_url), cover, desc, tags(list|comma), photos(list), format, user_id
    - FormData (multipart): ті ж самі поля +
        stl_file (файл моделі), stl_url
        cover_file (файл обкладинки), cover_url
    """

    title = ""
    price = 0
    file_url = ""
    cover = ""
    desc = ""
    fmt = "stl"
    tags_str = ""
    photos = []
    user_id = 0

    # ---- 1) multipart/form-data (форма з файлами) ----
    if request.files or (request.content_type or "").startswith("multipart/form-data"):
        form = request.form

        title = (form.get("title") or "").strip()
        price = _parse_int(form.get("price"), 0)
        desc  = (form.get("desc") or "").strip()
        fmt   = (form.get("format") or "stl").strip().lower()

        # tags: або JSON-рядок ["a","b"], або "a,b"
        raw_tags = form.get("tags") or ""
        try:
            parsed = json.loads(raw_tags) if raw_tags.strip().startswith("[") else raw_tags
            if isinstance(parsed, list):
                tags_str = ",".join([str(t).strip() for t in parsed if str(t).strip()])
            else:
                tags_str = str(parsed)
        except Exception:
            tags_str = str(raw_tags)

        # джерела моделі: файл або URL
        stl_file = request.files.get("stl_file")
        stl_url  = (form.get("stl_url") or form.get("url") or "").strip()
        saved_model = _save_file(stl_file, "models", ALLOWED_MODEL_EXT) if stl_file else None
        file_url = saved_model or stl_url

        # обкладинка: файл або URL (плейсхолдер, якщо порожньо)
        cover_file = request.files.get("cover_file")
        cover_url  = (form.get("cover_url") or form.get("cover") or "").strip()
        saved_cover = _save_file(cover_file, "covers", ALLOWED_IMG_EXT) if cover_file else None
        cover = saved_cover or cover_url or "/static/img/placeholder.jpg"

        # користувач
        user_id = _parse_int(form.get("user_id"), 0)
        if not user_id:
            user_id = _parse_int(session.get("user_id"), 0)

    else:
        # ---- 2) application/json ----
        data = request.get_json(silent=True) or {}

        title = (data.get("title") or "").strip()
        price = _parse_int(data.get("price"), 0)
        file_url = (data.get("url") or data.get("file_url") or "").strip()
        cover = (data.get("cover") or "").strip() or "/static/img/placeholder.jpg"
        desc = (data.get("desc") or "").strip()
        fmt = (data.get("format") or "stl").strip().lower()

        tags = data.get("tags") or ""
        if isinstance(tags, list):
            tags_str = ",".join([str(t).strip() for t in tags if str(t).strip()])
        else:
            tags_str = str(tags)

        photos = data.get("photos") or []
        user_id = _parse_int(data.get("user_id"), 0)
        if not user_id:
            user_id = _parse_int(session.get("user_id"), 0)

    # fallback: якщо все ще немає user_id — підхопимо першого користувача
    if not user_id:
        try:
            user_id = _parse_int(
                db.session.execute(text(f"SELECT id FROM {USERS_TBL} ORDER BY id ASC LIMIT 1")).scalar(),
                0
            )
        except Exception:
            user_id = 0

    # валідація мінімуму
    if not title or not file_url or not user_id:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    row = db.session.execute(
        text(f"""
            INSERT INTO {ITEMS_TBL}
              (title, desc, price, tags, cover, photos, file_url, format, downloads, user_id, created_at, updated_at)
            VALUES
              (:title, :desc, :price, :tags, :cover, CAST(:photos AS JSON), :file_url, :format, 0, :user_id, NOW(), NOW())
            RETURNING id
        """),
        {
            "title": title,
            "desc": desc,
            "price": price,
            "tags": tags_str,
            "cover": cover,
            "photos": json_dumps_safe(photos),
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

# -------------------- tiny util --------------------

def json_dumps_safe(obj) -> str:
    """Повертає JSON-строку для вставки у CAST(:photos AS JSON)."""
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "[]"

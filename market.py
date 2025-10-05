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

import math
from typing import Any, Dict, List, Optional

from flask import Blueprint, render_template, jsonify, request, session, abort
from sqlalchemy import text

from db import db, User

bp = Blueprint("market", __name__)

ITEMS_TBL = "items"
USERS_TBL = getattr(User, "__tablename__", "users") or "users"


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
    Очікує JSON: title, price, url(file_url), cover, desc, tags (comma or list),
                 photos (list), format, user_id (якщо не передали — беремо з session.user_id)
    """
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    price = _parse_int(data.get("price"), 0)
    file_url = (data.get("url") or data.get("file_url") or "").strip()
    cover = (data.get("cover") or "").strip()
    desc = (data.get("desc") or "").strip()
    fmt = (data.get("format") or "stl").strip().lower()

    # tags може прийти списком або строкою
    tags = data.get("tags") or ""
    if isinstance(tags, list):
        tags_str = ",".join([str(t).strip() for t in tags if str(t).strip()])
    else:
        tags_str = str(tags)

    photos = data.get("photos") or []

    user_id = _parse_int(data.get("user_id"), 0)
    if not user_id:
        user_id = _parse_int(session.get("user_id"), 0)

    # валідація мінімуму
    if not title or not file_url or not user_id:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    # вставка
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
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "[]"

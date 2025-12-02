import os
import math
import json
import shutil
import uuid
from typing import Any, Dict, Optional

from flask import Blueprint, render_template, jsonify, request, session, current_app, send_from_directory, abort, redirect, g
from sqlalchemy import text
from sqlalchemy import exc as sa_exc
from werkzeug.utils import secure_filename

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
from models import db, MarketItem
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

# логічний шлях; фізично пишемо у app/static/... всередині _save_upload
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
    """
    Приймає як новий шлях (/media/...), так і старий (/static/market_uploads/...).
    Перевіряє, чи файл є в static/market_uploads/...
    """
    if not media_url:
        return False

    rel = None
    if media_url.startswith("/media/"):
        rel = media_url[len("/media/"):].lstrip("/")
    elif media_url.startswith("/static/market_uploads/"):
        rel = media_url[len("/static/market_uploads/"):].lstrip("/")
    else:
        return False

    abs_path = os.path.join(current_app.root_path, "static", "market_uploads", rel)
    return os.path.isfile(abs_path)


def _normalize_cover_url(url: Optional[str]) -> str:
    """
    Повертає валідний URL обкладинки:
    - http(s)/data: — як є
    - /media/... — ДОВІРЯЄМО (без перевірок)
    - /static/market_uploads/... — одразу переписуємо в /media/... (без перевірок)
    - інакше — плейсхолдер
    """
    u = (url or "").strip()
    if not u:
        return COVER_PLACEHOLDER

    if u.startswith(("http://", "https://", "data:")):
        return u

    # ✅ довіряємо опублікованим локальним медіашляхам
    if u.startswith("/media/"):
        return u

    # ✅ старі шляхи відразу транслюємо у /media/ без перевірки існування
    if u.startswith("/static/market_uploads/"):
        rest = u[len("/static/market_uploads/"):].lstrip("/")
        return f"/media/{rest}"

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
                current_app.logger.warning(
                    f"Cloudinary upload failed, fallback to local: {type(_e).__name__}: {_e}"
                )
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


# ───────────────────────────── NEW: категорії в g ─────────────────────────────
@bp.before_app_request
def _inject_market_categories():
    """
    Підкидаємо g.market_categories на сторінках маркету,
    щоб друга шапка мала список категорій без зайвих запитів у в’юшках.
    """
    p = request.path or ""
    if not (p.startswith("/market") or p.startswith("/api/market")):
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
    # якщо в URL ?owner=me / my / mine — показуємо сторінку "Мої оголошення"
    owner = (request.args.get("owner") or "").strip().lower()
    if owner in ("me", "my", "mine"):
        return render_template("market/my.html")
    # ✅ рендеримо новий список маркету (всі моделі)
    return render_template("market/index.html")


@bp.get("/market/mine")
def page_market_mine():
    # старий шлях, залишаємо як є (якщо шаблон є)
    return render_template("market_mine.html")


# 🔥 НОВИЙ РОУТ: сторінка "Мої оголошення" (templates/market/my.html)
@bp.get("/market/my")
def page_market_my():
    """Render My Ads page with server-side data."""
    uid = _parse_int(session.get("user_id"), 0)
    my_ads = []
    
    if uid:
        # Fetch user's ads from database (only ads owned by the user)
        where_clause = "WHERE user_id = :uid"
        sql = f"""
            SELECT id, title, price, tags,
                   COALESCE(cover_url, '') AS cover,
                   stl_main_url AS url,
                   user_id, created_at
            FROM {ITEMS_TBL}
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT 100
        """
        try:
            rows = db.session.execute(text(sql), {"uid": uid}).fetchall()
            my_ads = [_row_to_dict(r) for r in rows]
            
            # Normalize cover URLs
            for ad in my_ads:
                c = _normalize_cover_url(ad.get("cover") or ad.get("cover_url"))
                ad["cover"] = c
                ad["thumbnail"] = c  # Add thumbnail field
                ad["thumb"] = c
                ad["image"] = c
        except Exception:
            db.session.rollback()
            my_ads = []
    
    return render_template("market/my.html", my_ads=my_ads)


@bp.get("/item/<int:item_id>")
def page_item(item_id: int):
    # ✅ беремо дані й робимо невеличкий бридж під новий detail.html
    it = _fetch_item_with_author(item_id)
    if not it:
        return render_template("item.html", item=None), 404

    d = dict(it)  # копія

    # owner-об’єкт для шаблону
    d["owner"] = {
        "name": d.get("author_name") or "-",
        "avatar_url": d.get("author_avatar") or "/static/img/user.jpg",
        "bio": d.get("author_bio") or "3D-дизайнер",
    }

    # відповідність полів ціни/безкоштовності
    if "price_cents" not in d:
        try:
            price_pln = float(d.get("price") or 0)
            d["price_cents"] = int(round(price_pln * 100))
        except Exception:
            d["price_cents"] = 0
    d["is_free"] = bool(d.get("is_free")) or (int(d.get("price_cents") or 0) == 0)

    # головний файл (для data-src)
    d["main_model_url"] = d.get("stl_main_url") or d.get("url")

    # обкладинка узгоджена
    d["cover_url"] = _normalize_cover_url(d.get("cover_url") or d.get("cover"))

    return render_template("market/detail.html", item=d)


# 🔧 сторінка завантаження (старий шлях /upload)
@bp.get("/upload")
def page_upload():
    # використовуємо вже існуючий шаблон templates/upload.html
    return render_template("upload.html")


# 🔧 додатковий шлях /market/upload, щоб працювали лінки з маркету
@bp.get("/market/upload")
def page_market_upload():
    # теж рендеримо той самий upload.html
    return render_template("upload.html")


@bp.get("/edit/<int:item_id>")
def page_edit_item(item_id: int):
    return render_template("market/edit.html")


@bp.get("/api/items")
def api_items():
    # безпечне strip/trim
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

    sql_new = f"""
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
    sql_new_min = f"""
        SELECT id, title, price, tags,
               {cover_expr} AS cover,
               {url_expr}   AS url,
               user_id, created_at
        FROM {ITEMS_TBL}
        {where_sql}
        {order_sql}
        LIMIT :limit OFFSET :offset
    """
    sql_legacy = f"""
        SELECT id, title, price, tags,
               COALESCE(cover, '')   AS cover,
               COALESCE(file_url,'') AS url,
               user_id, created_at
        FROM {ITEMS_TBL}
        {where_sql}
        {order_sql}
        LIMIT :limit OFFSET :offset
    """

    try:
        rows = db.session.execute(
            text(sql_new),
            {**params, "limit": per_page, "offset": offset}
        ).fetchall()
        items = [_row_to_dict(r) for r in rows]
    except sa_exc.ProgrammingError:
        db.session.rollback()
        try:
            rows = db.session.execute(
                text(sql_new_min),
                {**params, "limit": per_page, "offset": offset}
            ).fetchall()
            items = []
            for r in rows:
                d = _row_to_dict(r)
                d.setdefault("rating", 0)
                d.setdefault("downloads", 0)
                items.append(d)
        except sa_exc.ProgrammingError:
            db.session.rollback()
            rows = db.session.execute(
                text(sql_legacy),
                {**params, "limit": per_page, "offset": offset}
            ).fetchall()
            items = []
            for r in rows:
                d = _row_to_dict(r)
                d.setdefault("rating", 0)
                d.setdefault("downloads", 0)
                items.append(d)

    # 🔧 Пост-обробка: валідний cover і сумісність із фронтом
    for it in items:
        c = _normalize_cover_url(it.get("cover") or it.get("cover_url"))
        it["cover"] = c
        it["cover_url"] = c  # 👈 фронт може читати саме це поле

    return jsonify({
        "items": items,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if per_page else 1,
        "total": total
    })


# ✅ СТАРИЙ ШЛЯХ ДЛЯ СУМІСНОСТІ: /api/market/items
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

    # 🔥 включаємо і старі записи без user_id
    where_clause = "WHERE (user_id = :uid OR user_id IS NULL OR user_id = 0)"

    sql_new = f"""
        SELECT id, title, price, tags,
               COALESCE(cover_url, '') AS cover,
               COALESCE(rating, 0) AS rating,
               COALESCE(downloads, 0) AS downloads,
               stl_main_url AS url,
               format, user_id, created_at
        FROM {ITEMS_TBL}
        {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
    """
    sql_new_min = f"""
        SELECT id, title, price, tags,
               COALESCE(cover_url, '') AS cover,
               stl_main_url As url,
               user_id, created_at
        FROM {ITEMS_TBL}
        {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
    """
    sql_legacy = f"""
        SELECT id, title, price, tags,
               COALESCE(cover, '') AS cover,
               COALESCE(file_url,'') AS url,
               user_id, created_at
        FROM {ITEMS_TBL}
        {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
    """
    try:
        rows = db.session.execute(
            text(sql_new),
            {"uid": uid, "limit": per_page, "offset": offset}
        ).fetchall()
        items = [_row_to_dict(r) for r in rows]
        total = db.session.execute(
            text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_clause}"),
            {"uid": uid}
        ).scalar() or 0
    except sa_exc.ProgrammingError:
        db.session.rollback()
        try:
            rows = db.session.execute(
                text(sql_new_min),
                {"uid": uid, "limit": per_page, "offset": offset}
            ).fetchall()
            items = []
            for r in rows:
                d = _row_to_dict(r)
                d.setdefault("rating", 0)
                d.setdefault("downloads", 0)
                items.append(d)
            total = db.session.execute(
                text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_clause}"),
                {"uid": uid}
            ).scalar() or 0
        except sa_exc.ProgrammingError:
            db.session.rollback()
            rows = db.session.execute(
                text(sql_legacy),
                {"uid": uid, "limit": per_page, "offset": offset}
            ).fetchall()
            items = []
            for r in rows:
                d = _row_to_dict(r)
                d.setdefault("rating", 0)
                d.setdefault("downloads", 0)
                items.append(d)
            total = db.session.execute(
                text(f"SELECT COUNT(*) FROM {ITEMS_TBL} {where_clause}"),
                {"uid": uid}
            ).scalar() or 0

    # 🔁 Fallback: якщо реально нічого немає — показуємо загальний список
    if not total:
        return api_items()

    for it in items:
        c = _normalize_cover_url(it.get("cover") or it.get("cover_url"))
        it["cover"] = c
        it["cover_url"] = c  # 👈 сумісність

    return jsonify({
        "items": items,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if per_page else 1,
        "total": total
    })


# ✅ СТАРИЙ ШЛЯХ ДЛЯ СУМІСНОСТІ: /api/market/my-items
@bp.get("/api/market/my-items")
def api_my_items_compat():
    return api_my_items()


# ✅ НОВИЙ ШЛЯХ ДЛЯ "Мої оголошення": /api/market/my
@bp.get("/api/market/my")
def api_my_items_my():
    return api_my_items()


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


# 🔥 НОВИЙ: API для редагування оголошення
@bp.post("/api/item/<int:item_id>/update")
def api_item_update(item_id: int):
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    # Підтримуємо і JSON, і form-data (без файлів, файли йдуть через /api/upload)
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form or {}

    fields: Dict[str, Any] = {}

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
            try:
                val = json.loads(tags_val) if isinstance(tags_val, str) and tags_val.strip().startswith("[") else tags_val
            except Exception:
                val = tags_val
            if isinstance(val, list):
                tags_str = ",".join([str(t).strip() for t in val if str(t).strip()])
            else:
                tags_str = str(val or "")
        fields["tags"] = tags_str

    if "cover" in data or "cover_url" in data:
        cv = (data.get("cover_url") or data.get("cover") or "").strip()
        fields["cover_url"] = cv

    # галерея картинок (масив -> JSON)
    if "gallery_urls" in data or "photos" in data:
        g_val = data.get("gallery_urls") or data.get("photos")
        if isinstance(g_val, str):
            try:
                g_val = json.loads(g_val)
            except Exception:
                g_val = [g_val]
        if not isinstance(g_val, list):
            g_val = []
        g_val = [str(x) for x in g_val if x]
        fields["gallery_urls"] = json_dumps_safe(g_val)

    # основний STL
    if "stl_main_url" in data or "url" in data or "file_url" in data:
        fields["stl_main_url"] = (data.get("stl_main_url") or data.get("url") or data.get("file_url") or "").strip()

    # додаткові STL
    if "stl_extra_urls" in data or "stl_files" in data:
        s_val = data.get("stl_extra_urls") or data.get("stl_files")
        if isinstance(s_val, str):
            try:
                s_val = json.loads(s_val)
            except Exception:
                s_val = [s_val]
        if not isinstance(s_val, list):
            s_val = []
        s_val = [str(x) for x in s_val if x]
        fields["stl_extra_urls"] = json_dumps_safe(s_val)

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


@bp.post("/api/upload")
def api_upload():
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        form, files = request.form, request.files
        title = (form.get("title") or "").strip()
        price = _parse_int(form.get("price"), 0)
        desc = (form.get("desc") or "").strip()
        fmt = (form.get("format") or "stl").strip().lower()

        raw_tags = form.get("tags") or ""
        try:
            tags_val = json.loads(raw_tags) if raw_tags.strip().startswith("[") else raw_tags
        except Exception:
            tags_val = raw_tags

        file_url = (form.get("stl_url") or (form.get("url") or "")).strip()
        zip_url = (form.get("zip_url") or "").strip()

        stl_extra_files = files.getlist("stl_files") if "stl_files" in files else []
        stl_urls = []

        uid = _parse_int(session.get("user_id"), 0)

        if not file_url and "stl_file" in files:
            saved = _save_upload(files["stl_file"], f"user_{uid}/models", ALLOWED_MODEL_EXT)
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

        if not cover and "cover_file" in files:
            saved = _save_upload(files["cover_file"], f"user_{uid}/covers", ALLOWED_IMAGE_EXT)
            if saved:
                cover = saved

        if gallery_files:
            for f in gallery_files[:5]:
                saved = _save_upload(f, f"user_{uid}/gallery", ALLOWED_IMAGE_EXT)
                if saved:
                    images.append(saved)

        user_id = _parse_int(form.get("user_id"), 0) or _parse_int(session.get("user_id"), 0)
    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        price = _parse_int(data.get("price"), 0)
        desc = (data.get("desc") or "").strip()
        fmt = (data.get("format") or "stl").strip().lower()
        file_url = (data.get("url") or data.get("file_url") or "").strip()
        zip_url = (data.get("zip_url") or "").strip()
        cover = (data.get("cover") or data.get("cover_url") or "").strip()
        tags_val = data.get("tags") or ""
        user_id = _parse_int(data.get("user_id"), 0) or _parse_int(session.get("user_id"), 0)
        photos_data = data.get("photos")
        if isinstance(photos_data, dict):
            images = list(photos_data.get("images", []))
            stl_urls = list(photos_data.get("stl", []))
        else:
            images = list(data.get("photos") or [])
            stl_urls = list(data.get("stl_files") or [])

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
        }
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
        row = db.session.execute(text(f"""
          SELECT i.*,
                 u.name AS author_name,
                 u.email AS author_email,
                 u.id AS author_id
          FROM {ITEMS_TBL} i
          LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
          WHERE i.id = :id
        """), {"id": item_id}).fetchone()

    if not row:
        return None

    d = _row_to_dict(row)
    d.setdefault("author_avatar", "/static/img/user.jpg")
    d.setdefault("author_bio", "3D-дизайнер")

    images: list = []
    stl_files: list = []
    try:
        ph = d.get("photos")
        if isinstance(ph, (dict, list)):
            data = ph
        else:
            data = json.loads(ph or "[]")
        if isinstance(data, list):
            images = [s for s in data if s]
        elif isinstance(data, dict):
            images = [s for s in (data.get("images") or []) if s]
            stl_files = [s for s in (data.get("stl") or []) if s]
    except Exception:
        images, stl_files = [], []

    if not images:
        try:
            g = d.get("gallery_urls")
            g_list = g if isinstance(g, list) else json.loads(g or "[]")
            if isinstance(g_list, list):
                images = [s for s in g_list if s]
        except Exception:
            pass
    if not stl_files:
        try:
            s = d.get("stl_extra_urls")
            s_list = s if isinstance(s, list) else json.loads(s or "[]")
            if isinstance(s_list, list):
                stl_files = [s for s in s_list if s]
        except Exception:
            pass

    if not d.get("cover"):
        d["cover"] = d.get("cover_url") or d.get("cover") or (images[0] if images else None)
    if not d.get("url"):
        d["url"] = d.get("stl_main_url") or d.get("file_url") or (stl_files[0] if stl_files else None)

    d["photos"] = images[:5]
    d["stl_files"] = stl_files[:5]

    # 🔧 Нормалізуємо cover + віддзеркалюємо у cover_url для фронта
    c = _normalize_cover_url(d.get("cover") or d.get("cover_url"))
    d["cover"] = c
    d["cover_url"] = c

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


# ✅ Публічний роут для медіа
@bp.get("/media/<path:fname>")
@bp.get("/market/media/<path:fname>")
@bp.get("/static/market_uploads/media/<path:fname>")
def market_media(fname: str):
    safe = os.path.normpath(fname).lstrip(os.sep)
    base_dir = os.path.join(current_app.root_path, "static", "market_uploads")
    abs_path = os.path.join(base_dir, safe)
    if not os.path.isfile(abs_path):
        # якщо просили зображення — віддаємо плейсхолдер замість 404
        low = safe.lower()
        if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return current_app.send_static_file("img/placeholder_stl.jpg")
        abort(404)

    mime = None
    low = safe.lower()
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

    return send_from_directory(base_dir, safe, mimetype=mime)

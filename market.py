import os
import math
import json
import shutil
from typing import Any, Dict, Optional

from flask import Blueprint, render_template, jsonify, request, session, current_app
from sqlalchemy import text
from sqlalchemy import exc as sa_exc
from werkzeug.utils import secure_filename

from db import db, User

bp = Blueprint("market", __name__)

ITEMS_TBL = "items"
USERS_TBL = getattr(User, "__tablename__", "users") or "users"

# логічний шлях; фізично пишемо у app/static/... всередині _save_upload
UPLOAD_DIR = os.path.join("static", "market_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_MODEL_EXT = {".stl", ".obj", ".ply", ".gltf", ".glb"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}

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

def _save_upload(file_storage, subdir: str, allowed_ext: set) -> Optional[str]:
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in allowed_ext:
        return None
    safe = secure_filename(os.path.basename(file_storage.filename)) or ("file" + ext)

    static_root = os.path.join(current_app.root_path, "static")
    folder = os.path.join(static_root, "market_uploads", subdir)
    os.makedirs(folder, exist_ok=True)

    name = safe
    base, e = os.path.splitext(name)
    dst = os.path.join(folder, name)
    i = 1
    while os.path.exists(dst):
        name = f"{base}_{i}{e}"
        dst = os.path.join(folder, name)
        i += 1

    file_storage.save(dst)
    rel = os.path.relpath(dst, static_root).replace("\\", "/")
    return f"/static/{rel}"

def json_dumps_safe(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "[]"


@bp.get("/market")
def page_market():
    return render_template("market.html")

# (опційно) окрема сторінка «Мої оголошення», якщо хочеш мати її окремо від /market
@bp.get("/market/mine")
def page_market_mine():
    # створи шаблон market_mine.html або можеш рендерити той самий market.html і керувати режимом на фронті
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

# --------- ДОДАНО: сторінка редагування ---------
@bp.get("/edit/<int:item_id>")
def page_edit_item(item_id: int):
    # Шаблон сам підтягне дані через /api/item/<id>
    return render_template("edit.html")
# -----------------------------------------------


@bp.get("/api/items")
def api_items():
    q = (request.args.get("q") or "").strip().lower()
    free = _normalize_free(request.args.get("free"))
    sort = _normalize_sort(request.args.get("sort"))
    page = max(1, _parse_int(request.args.get("page"), 1))
    per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))

    # діалектно-безпечні вирази (tags може бути JSON у PG)
    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        title_expr = "LOWER(COALESCE(CAST(title AS TEXT), ''))"
        tags_expr  = "LOWER(COALESCE(CAST(tags  AS TEXT), ''))"
    else:
        title_expr = "LOWER(COALESCE(title, ''))"
        tags_expr  = "LOWER(COALESCE(tags,  ''))"

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

    sql_primary = f"""
        SELECT id, title, price, tags, cover, rating, downloads,
               file_url AS url, format, user_id, created_at
        FROM {ITEMS_TBL}
        {where_sql}
        {order_sql}
        LIMIT :limit OFFSET :offset
    """
    sql_fallback = f"""
        SELECT id, title, price, tags, cover, downloads,
               file_url AS url, format, user_id, created_at
        FROM {ITEMS_TBL}
        {where_sql}
        {order_sql}
        LIMIT :limit OFFSET :offset
    """
    try:
        rows = db.session.execute(
            text(sql_primary),
            {**params, "limit": per_page, "offset": offset}
        ).fetchall()
        items = [_row_to_dict(r) for r in rows]
    except sa_exc.ProgrammingError:
        db.session.rollback()
        rows = db.session.execute(
            text(sql_fallback),
            {**params, "limit": per_page, "offset": offset}
        ).fetchall()
        items = []
        for r in rows:
            d = _row_to_dict(r)
            d.setdefault("rating", 0)
            items.append(d)

    return jsonify({
        "items": items,
        "page": page,
        "per_page": per_page,
        "pages": math.ceil(total / per_page) if per_page else 1,
        "total": total
    })

# ---------- НОВЕ: список тільки моїх оголошень з пагінацією (з fallback як у /api/items) ----------
@bp.get("/api/my/items")
def api_my_items():
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"error": "unauthorized"}), 401

    page = max(1, _parse_int(request.args.get("page"), 1))
    per_page = min(60, max(6, _parse_int(request.args.get("per_page"), 24)))
    offset = (page - 1) * per_page

    try:
        total = db.session.execute(
            text(f"SELECT COUNT(*) FROM {ITEMS_TBL} WHERE user_id = :uid"),
            {"uid": uid}
        ).scalar() or 0

        sql_primary = f"""
            SELECT id, title, price, tags, cover, rating, downloads,
                   file_url AS url, format, user_id, created_at
            FROM {ITEMS_TBL}
            WHERE user_id = :uid
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
        """
        rows = db.session.execute(
            text(sql_primary),
            {"uid": uid, "limit": per_page, "offset": offset}
        ).fetchall()
        items = [_row_to_dict(r) for r in rows]

    except sa_exc.ProgrammingError:
        # якщо, наприклад, немає колонки rating
        db.session.rollback()
        sql_fallback = f"""
            SELECT id, title, price, tags, cover, downloads,
                   file_url AS url, format, user_id, created_at
            FROM {ITEMS_TBL}
            WHERE user_id = :uid
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
        """
        rows = db.session.execute(
            text(sql_fallback),
            {"uid": uid, "limit": per_page, "offset": offset}
        ).fetchall()
        items = []
        for r in rows:
            d = _row_to_dict(r)
            d.setdefault("rating", 0)
            items.append(d)

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "server", "detail": str(e)}), 500

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

# ---------- НОВЕ: видалення (тільки власник) ----------
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


@bp.post("/api/upload")
def api_upload():
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        form, files = request.form, request.files
        title = (form.get("title") or "").strip()
        price = _parse_int(form.get("price"), 0)
        desc  = (form.get("desc") or "").strip()
        fmt   = (form.get("format") or "stl").strip().lower()

        raw_tags = form.get("tags") or ""
        try:
            tags_val = json.loads(raw_tags) if raw_tags.strip().startswith("[") else raw_tags
        except Exception:
            tags_val = raw_tags

        # ------- STL -------
        file_url = (form.get("stl_url") or (form.get("url") or "")).strip()
        stl_extra_files = files.getlist("stl_files") if "stl_files" in files else []
        stl_urls = []

        if not file_url and "stl_file" in files:
            uid = _parse_int(session.get("user_id"), 0)
            saved = _save_upload(files["stl_file"], f"user_{uid}/models", ALLOWED_MODEL_EXT)
            if saved:
                file_url = saved

        if stl_extra_files:
            uid = _parse_int(session.get("user_id"), 0)
            for f in stl_extra_files[:5]:  # запас: якщо бек зашле 5 — все одно обмежимо
                saved = _save_upload(f, f"user_{uid}/models", ALLOWED_MODEL_EXT)
                if saved:
                    stl_urls.append(saved)
        # file_url головний, у stl_urls — додаткові (разом до 5 по шаблону)

        # ------- ФОТО -------
        cover = (form.get("cover_url") or "").strip()
        gallery_files = files.getlist("gallery_files") if "gallery_files" in files else []
        images = []

        if not cover and "cover_file" in files:
            uid = _parse_int(session.get("user_id"), 0)
            saved = _save_upload(files["cover_file"], f"user_{uid}/covers", ALLOWED_IMAGE_EXT)
            if saved:
                cover = saved

        if gallery_files:
            uid = _parse_int(session.get("user_id"), 0)
            for f in gallery_files[:5]:
                saved = _save_upload(f, f"user_{uid}/gallery", ALLOWED_IMAGE_EXT)
                if saved:
                    images.append(saved)

        user_id = _parse_int(form.get("user_id"), 0) or _parse_int(session.get("user_id"), 0)
    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        price = _parse_int(data.get("price"), 0)
        desc  = (data.get("desc") or "").strip()
        fmt   = (data.get("format") or "stl").strip().lower()
        file_url = (data.get("url") or data.get("file_url") or "").strip()
        cover = (data.get("cover") or "").strip()
        tags_val = data.get("tags") or ""
        user_id = _parse_int(data.get("user_id"), 0) or _parse_int(session.get("user_id"), 0)
        # API JSON: очікуємо опційні масиви
        images = list((data.get("photos") or {}).get("images", [])) if isinstance(data.get("photos"), dict) else (data.get("photos") or [])
        stl_urls = list((data.get("photos") or {}).get("stl", [])) if isinstance(data.get("photos"), dict) else list(data.get("stl_files") or [])

    if not cover:
        cover = COVER_PLACEHOLDER

    if isinstance(tags_val, list):
        tags_str = ",".join([str(t).strip() for t in tags_val if str(t).strip()])
    else:
        tags_str = str(tags_val or "")

    # головний STL обовʼязковий
    if not title or not file_url or not user_id:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    # обмеження 5/5 і пакуємо у JSON-колонку photos
    images = (images or [])[:5]
    stl_urls = (stl_urls or [])[:5]
    photos_payload = {"images": images, "stl": stl_urls}
    photos_json = json_dumps_safe(photos_payload)

    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        sql = f"""
            INSERT INTO {ITEMS_TBL}
              (title, "desc", price, tags, cover, photos, file_url, format,
               downloads, user_id, created_at, updated_at)
            VALUES
              (:title, :desc, :price, :tags, :cover, CAST(:photos AS JSON),
               :file_url, :format, 0, :user_id, NOW(), NOW())
            RETURNING id
        """
    else:
        sql = f"""
            INSERT INTO {ITEMS_TBL}
              (title, "desc", price, tags, cover, photos, file_url, format,
               downloads, user_id, created_at, updated_at)
            VALUES
              (:title, :desc, :price, :tags, :cover, :photos,
               :file_url, :format, 0, :user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

    row = db.session.execute(
        text(sql),
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
    )
    if dialect == "postgresql":
        new_id = _row_to_dict(row.fetchone())["id"]
    else:
        new_id = db.session.execute(text("SELECT last_insert_rowid() AS id")).scalar()

    db.session.commit()
    return jsonify({"ok": True, "id": int(new_id)})


def _fetch_item_with_author(item_id: int) -> Optional[Dict[str, Any]]:
    sql_primary = f"""
      SELECT i.*, 
             i.file_url AS url,
             u.name   AS author_name,
             u.email  AS author_email,
             u.id     AS author_id,
             COALESCE(u.avatar_url, '/static/img/user.jpg') AS author_avatar,
             COALESCE(u.bio, '3D-дизайнер') AS author_bio
      FROM {ITEMS_TBL} i
      LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
      WHERE i.id = :id
    """
    sql_fallback = f"""
      SELECT i.*, 
             i.file_url AS url,
             u.name   AS author_name,
             u.email  AS author_email,
             u.id     AS author_id
      FROM {ITEMS_TBL} i
      LEFT JOIN {USERS_TBL} u ON u.id = i.user_id
      WHERE i.id = :id
    """
    try:
        row = db.session.execute(text(sql_primary), {"id": item_id}).fetchone()
    except sa_exc.ProgrammingError:
        db.session.rollback()
        row = db.session.execute(text(sql_fallback), {"id": item_id}).fetchone()

    if not row:
        return None

    d = _row_to_dict(row)
    d.setdefault("author_avatar", "/static/img/user.jpg")
    d.setdefault("author_bio", "3D-дизайнер")

    # ---- Розпаковуємо photos: підтримуємо старий формат (масив) і новий (об’єкт) ----
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

    # якщо немає cover — ставимо перше фото
    if not d.get("cover") and images:
        d["cover"] = images[0]

    d["photos"] = images[:5]
    d["stl_files"] = stl_files[:5]
    # url вже виставлено як i.file_url AS url (головний STL)

    return d


# ====================== ДОДАНО НИЖЧЕ ======================

@bp.record_once
def _mount_persistent_uploads(setup_state):
    """
    Якщо задано UPLOADS_ROOT (env або app.config) — робимо симлінк:
      <app>/static/market_uploads  ->  UPLOADS_ROOT

    Якщо папка static/market_uploads вже існує (не симлінк), мігруємо її вміст
    у персистентний том і замінюємо на симлінк. Так файли не губляться після перезапусків.
    """
    app = setup_state.app
    persist_root = app.config.get("UPLOADS_ROOT") or os.environ.get("UPLOADS_ROOT")
    if not persist_root:
        # Можеш у Railway задати UPLOADS_ROOT=/data/market_uploads
        return
    try:
        os.makedirs(persist_root, exist_ok=True)
        static_root = os.path.join(app.root_path, "static")
        os.makedirs(static_root, exist_ok=True)
        link_path = os.path.join(static_root, "market_uploads")

        if os.path.islink(link_path):
            # вже посилання — нічого не робимо
            return

        if os.path.isdir(link_path):
            # мігруємо поточний вміст у персистентний том
            for name in os.listdir(link_path):
                src = os.path.join(link_path, name)
                dst = os.path.join(persist_root, name)
                if not os.path.exists(dst):
                    shutil.move(src, dst)
            # прибираємо папку і ставимо симлінк
            os.rmdir(link_path)

        if not os.path.exists(link_path):
            os.symlink(persist_root, link_path, target_is_directory=True)
    except Exception as e:
        app.logger.error("UPLOADS_ROOT mount failed: %r", e)


@bp.before_app_request
def _static_market_uploads_fallback():
    """
    Якщо браузер просить /static/market_uploads/... а файлу нема,
    повертаємо плейсхолдер з /static/img/placeholder_stл.jpg.
    Це запобігає «битим» картинкам, навіть якщо старі файли зникли.
    """
    p = request.path
    if request.method != "GET":
        return
    if not p.startswith("/static/market_uploads/"):
        return
    fs_path = os.path.join(current_app.root_path, p.lstrip("/"))
    if not os.path.exists(fs_path):
        # Віддаємо плейсхолдер з каталогу static
        return current_app.send_static_file("img/placeholder_stl.jpg")

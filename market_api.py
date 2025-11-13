# market_api.py
# Blueprint JSON API для розділу маркету.
# Підключення в app.py:
#   from market_api import bp as market_api_bp
#   app.register_blueprint(market_api_bp)

from __future__ import annotations
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

from flask import Blueprint, request, jsonify, current_app, url_for, abort
from flask_login import current_user, login_required
from sqlalchemy import func  # 👈 додано для сортування/агрегації

from models_market import (
    db,
    MarketItem,
    MarketCategory,
    Favorite,
    Review,
    recompute_item_rating,
)

bp = Blueprint("market_api", __name__, url_prefix="/api/market")


# ───────────────────────── ХЕЛПЕРИ ─────────────────────────

def _json_error(message: str, status: int = 400):
    resp = jsonify({"ok": False, "error": message})
    resp.status_code = status
    return resp


def _ensure_upload_dir() -> Path:
    """
    Локальне збереження файлів у static/uploads (для демо).
    На продакшені краще CDN (Cloudinary/S3).
    """
    root = Path(current_app.static_folder) / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(orig_name: str) -> str:
    ext = os.path.splitext(orig_name)[1].lower()
    token = secrets.token_hex(8)
    return f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{token}{ext}"


def _save_file(file_storage) -> Tuple[str, int]:
    """
    Зберігає файл у static/uploads, повертає (url, size_bytes).
    """
    updir = _ensure_upload_dir()
    fname = _safe_name(file_storage.filename or "file.bin")
    fpath = updir / fname
    file_storage.save(fpath)
    rel = f"uploads/{fname}"
    url = url_for("static", filename=rel, _external=False)
    try:
        size = fpath.stat().st_size
    except Exception:
        size = 0
    return url, size


def _coerce_bool(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


def _current_user_id_or_401() -> int:
    if not current_user.is_authenticated:
        abort(401)
    return int(current_user.id)


def _files_json_to_list(files_json: Optional[str]) -> List[Dict[str, Any]]:
    try:
        return json.loads(files_json or "[]")
    except Exception:
        return []


def _item_to_dict(it: MarketItem, *, include_files: bool = False, is_fav: bool = False) -> Dict[str, Any]:
    """
    Базова серіалізація товару для гріда/детейлу.
    JS може брати поля:
      id, slug, title, cover_url, price_cents, is_free, rating, downloads,
      created_at, category_slug, owner_id, is_fav, files[]
    """
    data: Dict[str, Any] = {
        "id": it.id,
        "slug": getattr(it, "slug", None),
        "title": it.title,
        "description": (it.description or ""),
        "cover_url": it.cover_url,
        "price_cents": getattr(it, "price_cents", 0),
        "is_free": getattr(it, "is_free", False),
        "rating": getattr(it, "rating", 0.0),
        "downloads": getattr(it, "downloads", 0),
        "created_at": it.created_at.isoformat() if getattr(it, "created_at", None) else None,
        "owner_id": getattr(it, "owner_id", None),
        "is_fav": bool(is_fav),
    }

    # категорія
    cat = None
    try:
        cat = it.category  # relationship if exists
    except Exception:
        cat = None
    if cat is not None:
        data["category_id"] = cat.id
        data["category_slug"] = getattr(cat, "slug", None)
        data["category_name"] = getattr(cat, "title", None)
    else:
        data["category_id"] = getattr(it, "category_id", None)

    if include_files:
        data["files"] = _files_json_to_list(it.files_json)

    return data


def _base_query():
    """Базовий запит по маркету з мінімальними фільтрами."""
    q = MarketItem.query

    # тільки опубліковані, якщо є прапор поля
    if hasattr(MarketItem, "is_published"):
        q = q.filter(MarketItem.is_published.is_(True))

    return q


# ──────────────────────── SUGGEST (GET) ─────────────────────

@bp.get("/suggest")
def suggest():
    """
    GET /api/market/suggest?q=dragon
    Повертає до 8 підказок за title.
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    items = (
        MarketItem.query
        .filter(MarketItem.title.ilike(f"%{q}%"))
        .order_by(MarketItem.downloads.desc(), MarketItem.created_at.desc())
        .limit(8)
        .all()
    )
    data = [{"title": it.title, "slug": it.slug} for it in items]
    return jsonify(data)


# ───────────────────────── LIST (GET) ───────────────────────

@bp.get("/items")
def items():
    """
    GET /api/market/items
    Параметри:
      q          – пошук по title/description
      page       – сторінка (1..)
      per_page   – кількість на сторінку (до 60)
      sort       – new | popular | top | price_asc | price_desc | free | paid
      category   – slug категорії
      owner_id   – фільтр по автору (для "Мої моделі" можна передати свій id)
      free       – 1/0 (примусово безкоштовні/платні)

    Відповідь:
      {
        ok: true,
        page: 1,
        pages: 3,
        total: 57,
        items: [ {...}, ... ]
      }
    """
    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "new").lower()
    category_slug = (request.args.get("category") or "").strip() or None
    owner_id = request.args.get("owner_id")
    free_filter = request.args.get("free")

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except Exception:
        page = 1

    try:
        per_page = int(request.args.get("per_page", 24))
    except Exception:
        per_page = 24
    per_page = max(1, min(per_page, 60))

    query = _base_query()

    # пошук
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            (MarketItem.title.ilike(pattern)) |
            (MarketItem.description.ilike(pattern))
        )

    # категорія
    if category_slug:
        cat = MarketCategory.query.filter_by(slug=category_slug).first()
        if cat:
            query = query.filter(MarketItem.category_id == cat.id)

    # автор
    if owner_id:
        try:
            oid = int(owner_id)
            query = query.filter(MarketItem.owner_id == oid)
        except Exception:
            pass

    # free/paid
    if free_filter is not None:
        flg = _coerce_bool(free_filter)
        query = query.filter(MarketItem.is_free.is_(flg))

    # сортування
    if sort == "popular":
        query = query.order_by(MarketItem.downloads.desc(), MarketItem.created_at.desc())
    elif sort == "top":
        if hasattr(MarketItem, "rating"):
            query = query.order_by(MarketItem.rating.desc(), MarketItem.downloads.desc())
        else:
            query = query.order_by(MarketItem.downloads.desc())
    elif sort == "price_asc":
        query = query.order_by(MarketItem.price_cents.asc(), MarketItem.created_at.desc())
    elif sort == "price_desc":
        query = query.order_by(MarketItem.price_cents.desc(), MarketItem.created_at.desc())
    elif sort == "free":
        query = query.filter(MarketItem.is_free.is_(True)).order_by(MarketItem.created_at.desc())
    elif sort == "paid":
        query = query.filter(MarketItem.is_free.is_(False)).order_by(MarketItem.created_at.desc())
    else:  # "new"
        query = query.order_by(MarketItem.created_at.desc())

    # пагінація
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items_list = pagination.items

    # фаворити юзера (щоб не робити 24 окремих запити)
    fav_ids: set[int] = set()
    if current_user.is_authenticated:
        fav_ids = {
            f.item_id
            for f in Favorite.query.filter_by(user_id=current_user.id).all()
        }

    data_items = [_item_to_dict(it, include_files=False, is_fav=(it.id in fav_ids)) for it in items_list]

    return jsonify({
        "ok": True,
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total,
        "items": data_items,
    })


# alias, якщо фронтенд звертається на /list
@bp.get("/list")
def items_alias():
    return items()


# ──────────────────────── DETAIL (GET) ──────────────────────

@bp.get("/item/<slug>")
def item_detail(slug: str):
    """
    GET /api/market/item/<slug>
    Детальна інформація про модель + останні відгуки.
    """
    it = MarketItem.query.filter_by(slug=slug).first()
    if not it:
        return _json_error("Item not found", 404)

    is_fav = False
    if current_user.is_authenticated:
        is_fav = Favorite.query.filter_by(
            user_id=current_user.id,
            item_id=it.id
        ).first() is not None

    item_data = _item_to_dict(it, include_files=True, is_fav=is_fav)

    # останні 10 відгуків
    reviews_q = (
        Review.query
        .filter_by(item_id=it.id)
        .order_by(Review.created_at.desc())
        .limit(10)
    )
    reviews_data = [{
        "id": r.id,
        "user_id": r.user_id,
        "rating": r.rating,
        "text": r.text,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in reviews_q]

    return jsonify({
        "ok": True,
        "item": item_data,
        "reviews": reviews_data,
    })


# ──────────────────────── MY ITEMS (GET) ────────────────────

@bp.get("/my")
@login_required
def my_items():
    """
    GET /api/market/my
    Повертає всі моделі поточного користувача (для вкладки "Мої оголошення").
    Параметри page/per_page підтримуються так само, як у /items.
    """
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except Exception:
        page = 1

    try:
        per_page = int(request.args.get("per_page", 24))
    except Exception:
        per_page = 24
    per_page = max(1, min(per_page, 60))

    query = _base_query().filter(MarketItem.owner_id == current_user.id)
    query = query.order_by(MarketItem.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items_list = pagination.items

    data_items = [_item_to_dict(it, include_files=False, is_fav=False) for it in items_list]

    return jsonify({
        "ok": True,
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total,
        "items": data_items,
    })


# ──────────────────────── FAVORITE (POST) ───────────────────

@bp.post("/fav")
@login_required
def fav():
    """
    POST /api/market/fav
    JSON: { "item_id": 123 }
    Тогл в обраному для поточного користувача.
    """
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("item_id")
    if not item_id:
        return _json_error("item_id is required", 400)

    it = MarketItem.query.get(item_id)
    if not it:
        return _json_error("Item not found", 404)

    existing = Favorite.query.filter_by(user_id=current_user.id, item_id=it.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"ok": True, "fav": False})

    fav_row = Favorite(user_id=current_user.id, item_id=it.id)
    db.session.add(fav_row)
    db.session.commit()
    return jsonify({"ok": True, "fav": True})


# ───────────────────────── UPLOAD (POST) ────────────────────

@bp.post("/upload")
@login_required
def upload():
    """
    POST multipart/form-data на /api/market/upload
    Поля:
      - title (str)
      - description (str, optional)
      - category_slug (str, optional)
      - is_free (bool-like)
      - price_cents (int, якщо не free)
      - cover (file, optional)
      - file (file) — головний 3D-файл (stl/obj/gltf/zip…)
    Відповідь:
      { ok: true, url: "/market/<slug>" }
    """
    form = request.form
    files = request.files

    title = (form.get("title") or "").strip() or "Untitled"
    description = (form.get("description") or "").strip()
    is_free = _coerce_bool(form.get("is_free", True))

    price_cents = 0
    if not is_free:
        try:
            price_cents = int(form.get("price_cents", "0"))
            if price_cents < 0:
                price_cents = 0
        except Exception:
            return _json_error("price_cents must be integer", 400)

    # категорія (не обов'язково)
    category_slug = (form.get("category_slug") or "").strip() or None
    category_id = None
    if category_slug:
        cat = MarketCategory.query.filter_by(slug=category_slug).first()
        if cat:
            category_id = cat.id

    # обкладинка (опц.)
    cover_url: Optional[str] = None
    cover_file = files.get("cover")
    if cover_file and cover_file.filename:
        # TODO: підключити Cloudinary тут замість локального сховища
        cover_url, _ = _save_file(cover_file)

    # головний файл (обов'язковий для нормального запису, але дозволяємо демо)
    main_url: Optional[str] = None
    main_kind: str = "file"
    main_file = files.get("file")
    files_json = []

    if main_file and main_file.filename:
        main_url, size = _save_file(main_file)
        # try визначити тип
        name = (main_file.filename or "").lower()
        if name.endswith(".stl"):  main_kind = "stl"
        elif name.endswith(".obj"): main_kind = "obj"
        elif name.endswith(".gltf") or name.endswith(".glb"): main_kind = "gltf"
        elif name.endswith(".ply"):  main_kind = "ply"
        elif name.endswith(".zip"):  main_kind = "zip"
        files_json.append({"url": main_url, "kind": main_kind, "size": size})

    # створюємо Item
    it = MarketItem(
        title=title,
        description=description,
        owner_id=_current_user_id_or_401(),
        category_id=category_id,
        cover_url=cover_url,
        files_json=json.dumps(files_json) if files_json else None,
        is_free=is_free,
        price_cents=price_cents,
    )
    it.ensure_slug()
    db.session.add(it)
    db.session.commit()

    # редірект URL
    url = url_for("market_detail", slug=it.slug)
    return jsonify({"ok": True, "url": url})


# ───────────────────────── REVIEW (POST) ────────────────────

@bp.post("/review")
@login_required
def review():
    """
    POST /api/market/review
    JSON: { "item_id": int, "rating": 1..5, "text": "..." }
    Якщо відгук цього користувача існує — оновлюємо.
    Перераховуємо середній рейтинг у MarketItem.
    """
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("item_id")
    rating = payload.get("rating")
    text = (payload.get("text") or "").strip()

    if not item_id:
        return _json_error("item_id is required", 400)
    try:
        rating = int(rating)
    except Exception:
        return _json_error("rating must be an integer", 400)

    if rating < 1 or rating > 5:
        return _json_error("rating must be 1..5", 400)

    it = MarketItem.query.get(item_id)
    if not it:
        return _json_error("Item not found", 404)

    row = Review.query.filter_by(item_id=item_id, user_id=current_user.id).first()
    if row:
        row.rating = rating
        row.text = text
    else:
        row = Review(item_id=item_id, user_id=current_user.id, rating=rating, text=text)
        db.session.add(row)

    db.session.commit()
    recompute_item_rating(item_id)
    return jsonify({"ok": True})


# ──────────────────────── CHECKOUT (POST) ───────────────────

@bp.post("/checkout")
@login_required
def checkout():
    """
    POST /api/market/checkout
    JSON: { "item_id": int }
    Плейсхолдер під Stripe/BLIK. Повертає демо-відповідь.
    TODO: створення Stripe Checkout Session і повернення session.url
    """
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("item_id")
    if not item_id:
        return _json_error("item_id is required", 400)

    it = MarketItem.query.get(item_id)
    if not it:
        return _json_error("Item not found", 404)

    if it.is_free or (it.price_cents or 0) == 0:
        # для безкоштовних — одразу "успіх"
        return jsonify({"ok": True, "free": True, "download_url": _extract_main_url(it)})

    # Заглушка: на проді тут робимо Stripe session і повертаємо URL
    return jsonify({"ok": True, "demo": True})
    # приклад для Stripe (коли підключиш):
    # return jsonify({"ok": True, "url": session.url})


def _extract_main_url(it: MarketItem) -> Optional[str]:
    try:
        arr = json.loads(it.files_json or "[]")
        return arr[0]["url"] if arr else None
    except Exception:
        return None


# ───────────────────────── TRACK (POST) ─────────────────────

@bp.post("/track")
def track():
    """
    POST /api/market/track
    JSON довільний, наприклад:
      { "type": "view" | "click" | "download" | "scroll", "slug": "...", "item_id": 123 }
    Мінімальний лог: не зберігаємо в БД, лише no-op 204.
    За бажанням під’єднай власну таблицю аналітики.
    """
    # payload = request.get_json(silent=True) or {}
    # current_app.logger.info({"event": "market", **payload})
    return ("", 204)


# ──────────────────────── ERROR HANDLERS ────────────────────

@bp.app_errorhandler(401)
def _handle_unauth(e):
    return _json_error("Unauthorized", 401)

@bp.app_errorhandler(404)
def _handle_404(e):
    return _json_error("Not found", 404)

@bp.app_errorhandler(405)
def _handle_405(e):
    return _json_error("Method not allowed", 405)

@bp.app_errorhandler(413)
def _handle_413(e):
    return _json_error("Payload too large", 413)

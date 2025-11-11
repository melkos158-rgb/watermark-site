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
from typing import Tuple, Optional

from flask import Blueprint, request, jsonify, current_app, url_for, abort
from flask_login import current_user, login_required

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

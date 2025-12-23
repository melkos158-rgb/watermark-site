from flask import abort


from flask import Blueprint, jsonify
bp = Blueprint("market_api", __name__)

# === LEGACY COMPAT: GET /api/my/items ===

from utils.market import build_cover_url


@bp.get("/my/items")
def api_my_items():
    from flask import request, session

    from models_market import MarketItem
    uid = session.get("user_id")
    if not uid:
        return jsonify(ok=False, error="auth_required"), 401
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 24))
    q = MarketItem.query.filter_by(user_id=uid)
    total = q.count()
    pages = (total + per_page - 1) // per_page
    items = q.order_by(MarketItem.id.desc()).offset((page-1)*per_page).limit(per_page).all()

    def serialize_item(it):
        return {
            "id": it.id,
            "title": getattr(it, "title", None),
            "price": getattr(it, "price", None),
            "cover_url": build_cover_url(it),
        }
    return jsonify(ok=True, items=[serialize_item(it) for it in items], page=page, pages=pages, total=total)

# === SERVE MEDIA FILES: /api/market/media/<id>/<filename> ===
@bp.get("/media/<int:item_id>/<path:filename>")
def api_market_media(item_id, filename):
    from flask import current_app, redirect, send_from_directory

    from models_market import MarketItem
    item = MarketItem.query.get(item_id)
    if not item:
        abort(404)
    cover_url = getattr(item, "cover_url", None) or ""
    if cover_url.startswith("/media/"):
        return redirect(cover_url, code=302)
    root = current_app.config.get("UPLOADS_ROOT") or "/data/market_uploads"
    item_dir = os.path.join(root, str(item_id))
    file_path = os.path.join(item_dir, filename)
    if not os.path.isfile(file_path):
        abort(404)
    return send_from_directory(item_dir, filename)

# === DIAGNOSTIC PING ENDPOINT ===
@bp.get("/ping")
def ping():
    from flask import current_app
    ep = None
    methods = None
    for r in current_app.url_map.iter_rules():
        if r.rule == "/market/upload":
            ep = r.endpoint
            methods = sorted(list(r.methods))
            break

    return jsonify(
        ok=True,
        route="/api/market/ping",
        market_upload_endpoint=ep,
        market_upload_methods=methods,
    )


from flask import Blueprint, current_app, request, session
from models_market import MarketItem, db

# === COMPAT GET /api/market/items ===
@bp.get("/items")
def api_market_items_compat():
    # Import and call the main /api/items handler from market.py
    from market import api_items
    return api_items()


# === POST /api/market/upload ===
@bp.post("/upload")
def api_market_upload():
    from flask import jsonify, request, session
    from db import db
    from models import MarketItem
    from upload_utils import upload_image, upload_stl, upload_video, upload_zip

    uid = session.get("user_id")
    if not uid:
        return jsonify({"ok": False, "error": "auth_required"}), 401

    try:
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        is_free = request.form.get("is_free") in ("1", "true", "on", True)
        price_cents = request.form.get("price_cents")
        try:
            price_cents = int(price_cents) if price_cents is not None else 0
        except Exception:
            price_cents = 0

        # Required file
        main_file = request.files.get("file")
        if not main_file:
            return jsonify({"ok": False, "error": "missing_file"}), 400

        # Optional files
        zip_file = request.files.get("zip_file")
        cover = request.files.get("cover")
        video = request.files.get("video")


        item = MarketItem(user_id=uid, title=title)
        # Assign description to the first available attribute
        for desc_field in ("description", "desc", "body", "details"):
            if hasattr(item, desc_field):
                setattr(item, desc_field, description)
                break
        if hasattr(item, "is_free"):
            item.is_free = is_free
        if hasattr(item, "price_cents"):
            item.price_cents = price_cents

        # Save main file (STL/OBJ/GLTF/ZIP)
        url, _ = upload_stl(main_file, folder="proofly/market/stl")
        if hasattr(item, "stl_main_url"):
            item.stl_main_url = url
        if hasattr(item, "format"):
            item.format = "stl"

        # Save optional files
        if zip_file:
            zip_url, _ = upload_zip(zip_file, folder="proofly/market/zip")
            if hasattr(item, "zip_url"):
                item.zip_url = zip_url
        if cover:
            cover_url, _ = upload_image(cover, folder="proofly/market/covers")
            if hasattr(item, "cover_url"):
                item.cover_url = cover_url
        if video:
            video_url, _ = upload_video(video, folder="proofly/market/video")
            if hasattr(item, "video_url"):
                item.video_url = video_url

        db.session.add(item)
        db.session.commit()

        return jsonify({"ok": True, "item_id": item.id, "redirect_url": "/market"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500

# === REAL DRAFT ENDPOINT ===
@bp.post("/items/draft")
def api_market_items_draft():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "auth"}), 401

    # Try to find existing draft in session
    draft_id = session.get("upload_draft_id")
    it = None
    if draft_id:
        try:
            draft_id = int(draft_id)
            it = MarketItem.query.get(draft_id)
        except Exception:
            it = None
    if it:
        session["upload_draft_id"] = int(it.id)
        session.modified = True
        return jsonify({"draft": {"id": it.id}}), 200

    # Create new draft
    item = MarketItem(
        user_id=uid,
        title=""
    )
    # Set status/state fields only if they exist
    if hasattr(item, "status"):
        item.status = "draft"
    if hasattr(item, "upload_status"):
        item.upload_status = "draft"
    if hasattr(item, "upload_progress"):
        item.upload_progress = 0
    if hasattr(item, "is_published"):
        item.is_published = False

    db.session.add(item)
    db.session.commit()
    session["upload_draft_id"] = int(item.id)
    session.modified = True

    current_app.logger.info(f"[UPLOAD] Draft created: {item.id}")

    return jsonify({
        "draft": {
            "id": item.id
        }
    }), 200

# ============================================================
#  PROOFLY MARKET – MAX POWER API
#  FULL SUPPORT FOR edit_model.js AUTOSAVE + FILE UPLOAD
# ============================================================

from models import MarketItem, _db
from upload_utils import upload_image, upload_stl, upload_video, upload_zip


def _parse_int(val, default=0):
    try:
        return int(val)
    except Exception:
        return default

@bp.post("/items/<int:item_id>/upload/<string:kind>")
def api_market_item_upload(item_id: int, kind: str):
    uid = _parse_int(session.get("user_id"), 0)
    if not uid:
        return jsonify({"error": "auth_required"}), 401

    kind = (kind or "").lower().strip()
    if kind not in {"cover", "stl", "zip", "video"}:
        return jsonify({"error": "bad_type"}), 400

    file = request.files.get("file")
    if not file or not getattr(file, "filename", ""):
        return jsonify({"error": "no_file"}), 400

    item = MarketItem.query.get(item_id)
    if not item or int(item.user_id or 0) != int(uid):
        return jsonify({"error": "not_found"}), 404

    try:
        if kind == "cover":
            url, _pid = upload_image(file, folder="proofly/market/covers")
            item.cover_url = url

        elif kind == "stl":
            url, _pid = upload_stl(file, folder="proofly/market/stl")
            item.stl_main_url = url
            item.format = "stl"

        elif kind == "zip":
            url, _pid = upload_zip(file, folder="proofly/market/zip")
            item.zip_url = url
            item.format = "zip"

        elif kind == "video":
            url, _pid = upload_video(file, folder="proofly/market/video")
            item.video_url = url

        _db.session.commit()
        return jsonify({"secure_url": url, "url": url}), 200

    except Exception as e:
        _db.session.rollback()
        return jsonify({"error": "upload_failed", "detail": str(e)}), 500



import os

# ...existing code from MAX POWER API section...

# ============================================================
# DEBUG ENDPOINT (TEMPORARY)
# ============================================================


@bp.get("/debug/item/<int:item_id>/files")
def debug_item_files_disk(item_id: int):
    """
    DEBUG: Show raw file URLs from database
    Use: /api/market/debug/item/41/files
    """
    it = MarketItem.query.get_or_404(item_id)
    return jsonify({
        "id": it.id,
        "stl_main_url": getattr(it, "stl_main_url", None),
        "stl_extra_urls": getattr(it, "stl_extra_urls", None),
        "zip_url": getattr(it, "zip_url", None),
        "cover_url": getattr(it, "cover_url", None),
        "gallery_urls": getattr(it, "gallery_urls", None),
    })

# ...rest of the code from the MAX POWER API section...

# === USER-OWNED ITEMS: GET /api/market/my/items ===
@bp.get("/my/items")
def api_market_my_items():
    from flask import jsonify, session

    from models_market import MarketItem
    uid = session.get("user_id")
    if not uid:
        return jsonify({"ok": False, "error": "auth"}), 401
    items = MarketItem.query.filter_by(user_id=uid).order_by(MarketItem.id.desc()).limit(50).all()
    out = []
    for it in items:
        out.append({
            "id": it.id,
            "title": getattr(it, "title", None) or getattr(it, "name", None) or f"Item {it.id}",
            "price": getattr(it, "price", 0) or 0,
            "cover_url": build_cover_url(it)
        })
    return jsonify({"ok": True, "items": out}), 200

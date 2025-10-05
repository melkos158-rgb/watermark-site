# market.py
import os, json
from flask import Blueprint, render_template, jsonify, request

bp = Blueprint("market", __name__)

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
ITEMS_JSON = os.path.join(DATA_DIR, "items.json")
USERS_JSON = os.path.join(DATA_DIR, "users.json")

def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- Сторінки ----------
@bp.get("/market")
def market():
    return render_template("market.html")

@bp.get("/item/<int:item_id>")
def item_page(item_id: int):
    items = _read_json(ITEMS_JSON, [])
    users = _read_json(USERS_JSON, [])
    it = next((x for x in items if x.get("id") == item_id), None)
    if not it:
        return render_template("item.html", item=None), 404
    author = next((u for u in users if u.get("id") == it.get("user_id")), None)
    it = {**it}
    if author:
        it["author_name"] = author.get("name")
        it["author_avatar"] = author.get("avatar")
        it["author_bio"] = author.get("bio", "3D-дизайнер")
        it["earnings"] = author.get("earnings_pln", 0)
        it["items_count"] = author.get("listings_count", 0)
    return render_template("item.html", item=it)

@bp.get("/upload")
def upload_page():
    return render_template("upload.html")

# ---------- API ----------
@bp.get("/api/items")
def api_items():
    q = (request.args.get("q") or "").lower().strip()
    free = (request.args.get("free") or "all").lower().strip()  # all|free|paid
    items = _read_json(ITEMS_JSON, [])

    out = []
    for it in items:
        title = (it.get("title") or "").lower()
        tags = [str(t).lower() for t in (it.get("tags") or [])]
        price = int(it.get("price") or 0)
        if q and (q not in title and not any(q in t for t in tags)):
            continue
        if free == "free" and price > 0:
            continue
        if free == "paid" and price == 0:
            continue
        out.append(it)
    return jsonify(out)

@bp.get("/api/item/<int:item_id>")
def api_item(item_id: int):
    items = _read_json(ITEMS_JSON, [])
    users = _read_json(USERS_JSON, [])
    it = next((x for x in items if x.get("id") == item_id), None)
    if not it:
        return jsonify({"error": "not_found"}), 404
    author = next((u for u in users if u.get("id") == it.get("user_id")), None)
    return jsonify({"item": it, "author": author})

@bp.post("/api/upload")
def api_upload():
    """
    Простий мок-додавання нового оголошення у items.json.
    Очікує JSON: title, price, user_id, url, (опц.) tags[], cover, photos[], desc, format
    """
    data = request.get_json(force=True, silent=True) or {}
    for k in ("title", "price", "user_id", "url"):
        if not data.get(k):
            return jsonify({"ok": False, "error": f"missing_{k}"}), 400

    items = _read_json(ITEMS_JSON, [])
    new_id = (max([it.get("id", 0) for it in items]) + 1) if items else 1
    rec = {
        "id": new_id,
        "title": data.get("title"),
        "price": int(data.get("price") or 0),
        "tags": data.get("tags") or [],
        "rating": float(data.get("rating") or 0),
        "user_id": int(data.get("user_id")),
        "url": data.get("url"),
        "format": data.get("format") or "stl",
        "cover": data.get("cover") or "",
        "photos": data.get("photos") or [],
        "desc": data.get("desc") or "",
        "downloads": int(data.get("downloads") or 0)
    }
    items.append(rec)
    _write_json(ITEMS_JSON, items)
    return jsonify({"ok": True, "id": new_id})

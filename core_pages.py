# core_pages.py
# Базові сторінки Proofly (головна, STL, фото/відео, документи, donate, health, media, robots).

import os

import stripe
from flask import (Blueprint, abort, current_app, jsonify, render_template,
                   request, send_from_directory)

bp = Blueprint("core", __name__)  # імʼя blueprint, але ендпоінти лишаємо як у тебе


# ───────────────────── ГОЛОВНІ СТОРІНКИ ─────────────────────

@bp.route("/", endpoint="index")
def index():
    return render_template("index.html")


@bp.route("/stl", endpoint="stl")
def stl():
    return render_template("stl.html")


@bp.route("/stl/viewer", endpoint="stl_viewer")
def stl_viewer():
    return render_template("stl_viewer.html")


@bp.route("/video", endpoint="video")
def video():
    return render_template("video.html")


@bp.route("/enhance", endpoint="enhance")
def enhance():
    return render_template("enhance.html")


@bp.route("/edit-photo", endpoint="edit_photo")
def edit_photo():
    return render_template("edit_photo.html")


@bp.route("/filters", endpoint="filters_page")
@bp.route("/filters.html", endpoint="filters_page_html")
def filters_page():
    # endpoint="filters_page" збережений для url_for('filters_page')
    return render_template("filters.html")


@bp.route("/photo", endpoint="photo")
def photo():
    return render_template("photo.html")


@bp.route("/documents", endpoint="documents")
@bp.route("/documents.html", endpoint="documents_html")
def documents():
    return render_template("documents.html")


# ───────────────────────── DONATE / STRIPE ──────────────────

@bp.route("/donate", endpoint="donate_page")
def donate_page():
    return render_template("donate.html")


@bp.post("/create-payment-intent", endpoint="create_payment_intent")
def create_payment_intent():
    """
    Створення Stripe PaymentIntent для донату.
    Логіка 1в1 як була в app.py, тільки через current_app.
    """
    if not current_app.config.get("STRIPE_SECRET_KEY"):
        return jsonify({"error": "stripe_not_configured"}), 500

    data = request.get_json(silent=True) or {}
    try:
        amount_pln = max(int(data.get("amount", 2)), 2)
    except Exception:
        amount_pln = 2

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_pln * 100,
            currency="pln",
            automatic_payment_methods={"enabled": True},
            description="Proofly Balance Top-Up (card)",
        )
        return jsonify(clientSecret=intent.client_secret)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/success", endpoint="success_page")
def success_page():
    tmpl_path = os.path.join(current_app.root_path, "templates", "success.html")
    if os.path.exists(tmpl_path):
        return render_template("success.html")
    return "<h2 style='color:#16a34a'>✅ Оплата успішна</h2>", 200


# ───────────────────── HEALTH / ROBOTS / MEDIA ──────────────

@bp.route("/healthz", endpoint="healthz")
def healthz():
    return "ok", 200


@bp.route("/health", endpoint="health")
def health():
    return "ok", 200


@bp.route("/robots.txt")
def robots_txt():
    """
    Сервить robots.txt зі static, або віддає дефолтний текст.
    """
    try:
        static_root = os.path.join(current_app.root_path, "static")
        return send_from_directory(static_root, "robots.txt")
    except Exception:
        text = "User-agent: *\nCrawl-delay: 5\n"
        return text, 200, {"Content-Type": "text/plain; charset=utf-8"}


@bp.route("/media/<path:filename>")
@bp.route("/market/media/<path:filename>")
@bp.route("/static/market_uploads/media/<path:filename>")
def media(filename):
    """
    Видає файли моделей/зображень з:
      - static/market_uploads
      - MEDIA_ROOT
      - static/
    + підбирає коректний mimetype.
    """
    safe = os.path.normpath(filename).lstrip(os.sep)

    roots = [
        os.path.join(current_app.root_path, "static", "market_uploads"),
        current_app.config.get(
            "MEDIA_ROOT",
            os.path.join(current_app.root_path, "media"),
        ),
        os.path.join(current_app.root_path, "static"),
    ]

    for root in roots:
        full = os.path.join(root, safe)
        if os.path.isfile(full):
            low = safe.lower()
            mimetype = None
            if low.endswith(".stl"):
                mimetype = "model/stl"
            elif low.endswith(".obj"):
                mimetype = "text/plain"
            elif low.endswith(".glb"):
                mimetype = "model/gltf-binary"
            elif low.endswith(".gltf"):
                mimetype = "model/gltf+json"
            elif low.endswith(".zip"):
                mimetype = "application/zip"
            elif low.endswith((".jpg", ".jpeg")):
                mimetype = "image/jpeg"
            elif low.endswith(".png"):
                mimetype = "image/png"
            elif low.endswith(".webp"):
                mimetype = "image/webp"

            return send_from_directory(root, safe, mimetype=mimetype)

    # якщо файл не знайшли, а це картинка — показуємо плейсхолдер
    low = safe.lower()
    if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
        placeholder_root = os.path.join(current_app.root_path, "static", "img")
        placeholder_name = "placeholder_stl.jpg"
        placeholder_abs = os.path.join(placeholder_root, placeholder_name)
        if os.path.isfile(placeholder_abs):
            return send_from_directory(
                placeholder_root,
                placeholder_name,
                mimetype="image/jpeg",
            )

    return abort(404)

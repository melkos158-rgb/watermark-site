import os
import threading
from flask import Flask, render_template, jsonify, request, session, send_from_directory, abort, g
from flask_babel import Babel  # ✅

from db import init_app_db, close_db, db, User
from models import db as models_db, MarketItem

from functools import wraps
from datetime import datetime
from werkzeug.utils import secure_filename
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

# === ADMIN CONFIG ===
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
UPLOAD_DIR = os.path.join("static", "ads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}

DEFAULT_BANNER_IMG = os.getenv("DEFAULT_BANNER_IMG", "ads/default_banner.jpg")
DEFAULT_BANNER_URL = os.getenv("DEFAULT_BANNER_URL", "")

USERS_TBL = getattr(User, "__tablename__", "users") or "users"


def to_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return default


def allowed_file(fname: str) -> bool:
    return "." in fname and fname.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def admin_required(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("is_admin"):
            from flask import redirect, url_for, flash
            flash("Доступ лише для адміністратора.")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return _wrap


# === Banner model ===
class BannerAd(db.Model):
    __tablename__ = "banner_ad"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    link_url = db.Column(db.String(500))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# === JSON login guard ===
def login_required_json(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"ok": False, "error": "auth_required"}), 401
        return f(*args, **kwargs)
    return inner


def row_to_dict(row):
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)


# === MAIN APP CREATOR ===
def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "devsecret-change-me")

    # ==== Babel (локаль) — FIX для Babel 3.x ====
    babel = Babel()  # створюємо інстанс без додекоратора

    def _get_locale():
        """Визначення поточної мови: user.lang → session['lang'] → 'uk'."""
        lang = None
        if session.get("user_id"):
            try:
                u = User.query.get(session["user_id"])
                if u and hasattr(u, "lang") and u.lang:
                    lang = (u.lang or "").lower()
            except Exception:
                pass
        if not lang:
            lang = (session.get("lang") or "uk").lower()
        return (lang[:8] or "uk")

    # реєструємо селектор через init_app (нова API)
    babel.init_app(app, locale_selector=_get_locale)

    # зробимо доступною мову у шаблонах
    @app.context_processor
    def _inject_current_lang():
        try:
            cur = _get_locale()
        except Exception:
            cur = (session.get("lang") or "uk")
        return dict(current_lang=cur)

    uploads_dir = os.path.join(app.root_path, "static", "market_uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    base_dir = os.path.abspath(os.path.dirname(__file__))
    app.config.setdefault("MEDIA_ROOT", os.path.join(base_dir, "media"))
    app.config.setdefault("MEDIA_URL", "/media/")
    os.makedirs(app.config["MEDIA_ROOT"], exist_ok=True)

    # Init DB
    init_app_db(app)
    app.teardown_appcontext(close_db)
    models_db.init_app(app)

    # === Ensure tables once ===
    _tables_ready_key = "FEEDBACK_TABLES_READY"
    _tables_lock = threading.Lock()
    app.config.setdefault(_tables_ready_key, False)

    def ensure_feedback_tables():
        """Create required tables if missing."""
        if not hasattr(db, "engine"):
            return
        dialect = db.engine.dialect.name
        with db.engine.begin() as conn:
            if dialect == "postgresql":
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS suggestions (
                      id SERIAL PRIMARY KEY,
                      user_id INTEGER NOT NULL,
                      title TEXT NOT NULL,
                      body TEXT,
                      likes INTEGER NOT NULL DEFAULT 0,
                      comments_count INTEGER NOT NULL DEFAULT 0,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS suggestion_votes (
                      id SERIAL PRIMARY KEY,
                      suggestion_id INTEGER NOT NULL,
                      user_id INTEGER NOT NULL,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                      CONSTRAINT suggestion_votes_uniq UNIQUE (suggestion_id, user_id)
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS suggestion_comments (
                      id SERIAL PRIMARY KEY,
                      suggestion_id INTEGER NOT NULL,
                      user_id INTEGER NOT NULL,
                      body TEXT NOT NULL,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS pxp_transactions (
                      id SERIAL PRIMARY KEY,
                      user_id INTEGER NOT NULL,
                      delta INTEGER NOT NULL,
                      reason TEXT NOT NULL,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS banner_ad (
                      id SERIAL PRIMARY KEY,
                      user_id INTEGER NOT NULL,
                      image_path VARCHAR(255) NOT NULL,
                      link_url VARCHAR(500),
                      active BOOLEAN NOT NULL DEFAULT TRUE,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS items (
                      id SERIAL PRIMARY KEY,
                      user_id INTEGER,
                      title VARCHAR(200),
                      price INTEGER DEFAULT 0,
                      tags TEXT DEFAULT '',
                      "description" TEXT DEFAULT '',
                      cover_url TEXT,
                      gallery_urls TEXT DEFAULT '[]',
                      stl_main_url TEXT,
                      stl_extra_urls TEXT DEFAULT '[]',
                      zip_url TEXT,
                      format VARCHAR(16) DEFAULT 'stl',
                      rating DOUBLE PRECISION DEFAULT 0,
                      downloads INTEGER DEFAULT 0,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                      updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                """))
                conn.execute(text("""ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT"""))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS suggestions (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      title TEXT NOT NULL,
                      body TEXT,
                      likes INTEGER NOT NULL DEFAULT 0,
                      comments_count INTEGER NOT NULL DEFAULT 0,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS banner_ad (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      image_path TEXT NOT NULL,
                      link_url TEXT,
                      active INTEGER NOT NULL DEFAULT 1,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS items (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      title TEXT,
                      price INTEGER DEFAULT 0,
                      tags TEXT DEFAULT '',
                      "description" TEXT DEFAULT '',
                      cover_url TEXT,
                      gallery_urls TEXT DEFAULT '[]',
                      stl_main_url TEXT,
                      stl_extra_urls TEXT DEFAULT '[]',
                      zip_url TEXT,
                      format TEXT DEFAULT 'stl',
                      rating REAL DEFAULT 0,
                      downloads INTEGER DEFAULT 0,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                try:
                    conn.execute(text("""ALTER TABLE users ADD COLUMN avatar_url TEXT"""))
                except Exception:
                    pass

    @app.before_request
    def _ensure_tables_once():
        if app.config.get(_tables_ready_key, False):
            return
        with _tables_lock:
            if app.config.get(_tables_ready_key, False):
                return
            try:
                ensure_feedback_tables()
            except Exception as e:
                print("[ensure_feedback_tables] skipped:", e)
            finally:
                app.config[_tables_ready_key] = True

    # === Blueprints ===
    import auth, profile, chat, market
    app.register_blueprint(auth.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(chat.bp)
    app.register_blueprint(market.bp)

    # === Mark admin ===
    @app.before_request
    def _mark_admin():
        uid = session.get("user_id")
        if not uid:
            session.pop("is_admin", None)
            return
        u = User.query.get(uid)
        if u and u.email and u.email.lower() in ADMIN_EMAILS:
            session["is_admin"] = True
        else:
            session.pop("is_admin", None)

    # === Banner logic ===
    def get_top1_user_this_month():
        if hasattr(User, "pxp_month"):
            u = User.query.order_by(User.pxp_month.desc(), User.id.asc()).first()
            if u:
                return u
        if hasattr(User, "pxp"):
            return User.query.order_by(User.pxp.desc(), User.id.asc()).first()
        return None

    def get_active_banner():
        top1 = get_top1_user_this_month()
        if top1:
            rec = BannerAd.query.filter_by(active=True, user_id=top1.id).order_by(BannerAd.id.desc()).first()
            if rec:
                return {"image_path": rec.image_path, "link_url": rec.link_url or ""}
        return {"image_path": DEFAULT_BANNER_IMG, "link_url": DEFAULT_BANNER_URL}

    # === Contexts ===
    @app.context_processor
    def inject_user():
        u = User.query.get(session["user_id"]) if session.get("user_id") else None
        return dict(current_user=u, pxp=(to_int(u.pxp) if u else 0))

    @app.context_processor
    def inject_banner():
        return dict(banner=get_active_banner())

    # === ⬇️ Admin metrics injected into templates
    @app.context_processor
    def _inject_admin_metrics():
        try:
            total_users = db.session.execute(
                text(f"SELECT COUNT(*) FROM {USERS_TBL}")
            ).scalar() or 0

            # Визначаємо діалект для сумісності
            dialect = getattr(getattr(db, "engine", None), "dialect", None)
            dialect_name = getattr(dialect, "name", "postgresql")

            if dialect_name == "sqlite":
                online_now = db.session.execute(text("""
                    SELECT COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), session_id))
                    FROM visits
                    WHERE datetime(created_at) >= datetime('now','-10 minutes')
                """)).scalar() or 0
                monthly_visitors = db.session.execute(text("""
                    SELECT COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), session_id))
                    FROM visits
                    WHERE date(created_at) >= date(strftime('%Y-%m-01','now'))
                """)).scalar() or 0
            else:
                online_now = db.session.execute(text("""
                    SELECT COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), session_id))
                    FROM visits
                    WHERE created_at >= NOW() - INTERVAL '10 minutes'
                """)).scalar() or 0
                monthly_visitors = db.session.execute(text("""
                    SELECT COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), session_id))
                    FROM visits
                    WHERE created_at >= date_trunc('month', NOW())
                """)).scalar() or 0

            return dict(admin_metrics={
                "total_users": int(total_users),
                "online_now": int(online_now),
                "monthly_visitors": int(monthly_visitors),
            })
        except Exception:
            return dict(admin_metrics={"total_users": 0, "online_now": 0, "monthly_visitors": 0})

    # === Pages ===
    @app.route("/", endpoint="index")
    def index():
        return render_template("index.html")

    @app.route("/stl")
    def stl():
        return render_template("stl.html")

    @app.route("/video")
    def video():
        return render_template("video.html")

    @app.route("/enhance")
    def enhance():
        return render_template("enhance.html")

    @app.route("/edit-photo")
    def edit_photo():
        return render_template("edit_photo.html")

    @app.route("/filters")
    @app.route("/filters.html")
    def filters_page():
        return render_template("filters.html")

    @app.route("/photo")
    def photo():
        return render_template("photo.html")

    @app.route("/documents")
    @app.route("/documents.html")
    def documents():
        return render_template("documents.html")

    # === Language API (нове, не чіпає існуючі) ===
    @app.post("/api/lang/set")
    def api_lang_set():
        data = request.get_json(silent=True) or {}
        lang = (data.get("lang") or "").lower()[:8]
        if not lang:
            return jsonify({"ok": False, "error": "no lang"}), 400

        session["lang"] = lang

        uid = session.get("user_id")
        if uid:
            try:
                u = User.query.get(uid)
                if u is not None and hasattr(u, "lang"):
                    setattr(u, "lang", lang)
                    db.session.add(u)
                    db.session.commit()
            except Exception:
                db.session.rollback()

        return jsonify({"ok": True, "lang": lang})

    @app.get("/api/lang/me")
    def api_lang_me():
        lang = None
        uid = session.get("user_id")
        if uid:
            try:
                u = User.query.get(uid)
                if u is not None and hasattr(u, "lang") and getattr(u, "lang"):
                    lang = (u.lang or "").lower()
            except Exception:
                pass
        if not lang:
            lang = (session.get("lang") or "uk").lower()
        return jsonify({"lang": (lang[:8] or "uk")})

    # === Banner management ===
    @app.route("/ad/click")
    def ad_click():
        if not session.get("user_id"):
            from flask import redirect, url_for, request
            return redirect(url_for("auth.login", next=request.path))
        b = get_active_banner()
        if b.get("link_url"):
            return redirect(b["link_url"])
        return redirect(url_for("index"))

    @app.route("/ad/upload", methods=["GET", "POST"])
    def ad_upload():
        from flask import redirect, url_for, flash, render_template
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        me = User.query.get(session["user_id"])
        top1 = get_top1_user_this_month()
        if not top1 or top1.id != me.id:
            flash("Завантажувати банер може лише користувач із TOP-1 цього місяця.")
            return redirect(url_for("index"))

        if request.method == "POST":
            f = request.files.get("image")
            link_url = request.form.get("link_url") or ""
            if not f or not allowed_file(f.filename):
                flash("Завантаж зображення .png/.jpg/.jpeg/.webp")
                return redirect(url_for("ad_upload"))

            fname = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"
            save_rel = os.path.join("ads", fname).replace("\\", "/")
            save_abs = os.path.join("static", save_rel)
            os.makedirs(os.path.dirname(save_abs), exist_ok=True)
            f.save(save_abs)

            BannerAd.query.filter_by(user_id=me.id, active=True).update({"active": False})
            db.session.add(BannerAd(user_id=me.id, image_path=save_rel, link_url=link_url, active=True))
            db.session.commit()
            flash("Банер оновлено! Він уже на головній.")
            return redirect(url_for("index"))

        return render_template("ad_upload_inline.html")

    # === Admin Panel ===
    @app.route("/admin", endpoint="admin_panel")
    @admin_required
    def admin_panel():
        return render_template("admin.html")

    # --- 🔧 ДОДАНІ URL-ПРАВИЛА ДЛЯ ШАБЛОНУ admin.html (без змін існуючих функцій) ---
    app.add_url_rule("/admin/reset-month",
                     endpoint="admin_reset_month",
                     view_func=admin_panel,
                     methods=["POST"])

    app.add_url_rule("/admin/pxp-add",
                     endpoint="admin_pxp_add",
                     view_func=admin_panel,
                     methods=["POST"])

    @app.route("/admin/disable-top-banner", methods=["POST"])
    @admin_required
    def admin_disable_top_banner():
        top1 = get_top1_user_this_month()
        if top1:
            BannerAd.query.filter_by(user_id=top1.id, active=True).update({"active": False})
            db.session.commit()
        from flask import redirect, url_for, flash
        flash("Банер TOP-1 вимкнено. Показується дефолтний.")
        return redirect(url_for("admin_panel"))

    @app.route("/admin/banner-default", methods=["POST"])
    @admin_required
    def admin_banner_default():
        from flask import request, redirect, url_for, flash
        f = request.files.get("image")
        link_url = request.form.get("link_url") or ""
        if not f or not allowed_file(f.filename):
            flash("Дай .png/.jpg/.jpeg/.webp")
            return redirect(url_for("admin_panel"))

        ext = f.filename.rsplit(".", 1)[1].lower()
        fname = f"default_banner.{ext}"
        save_rel = os.path.join("ads", fname).replace("\\", "/")
        save_abs = os.path.join("static", save_rel)
        os.makedirs(os.path.dirname(save_abs), exist_ok=True)
        f.save(save_abs)

        global DEFAULT_BANNER_IMG, DEFAULT_BANNER_URL
        DEFAULT_BANNER_IMG = save_rel
        DEFAULT_BANNER_URL = link_url

        flash("Дефолтний банер оновлено.")
        return redirect(url_for("admin_panel"))

    # === ⬇️ lightweight visits tracker
    from time import time as _now

    @app.before_request
    def _track_visit():
        try:
            sid = session.get("sid")
            if not sid:
                sid = os.urandom(16).hex()
                session["sid"] = sid

            last_ts = session.get("_last_visit_ts") or 0
            if _now() - float(last_ts) < 60:
                return
            session["_last_visit_ts"] = _now()

            uid = session.get("user_id")
            pth = (request.path or "/")[:255]

            # явний created_at = NOW() для коректного підрахунку "онлайн"
            db.session.execute(
                text("INSERT INTO visits (session_id, user_id, path, created_at) VALUES (:sid, :uid, :pth, NOW())"),
                {"sid": sid, "uid": uid, "pth": pth}
            )
            db.session.commit()
        except Exception:
            db.session.rollback()

    # === Healthcheck ===
    @app.route("/healthz")
    def healthz():
        return "ok", 200

    # === Media route ===
    @app.route("/media/<path:filename>")
    @app.route("/market/media/<path:filename>")
    @app.route("/static/market_uploads/media/<path:filename>")  # ⬅️ сумісність зі старими URL
    def media(filename):
        safe = os.path.normpath(filename).lstrip(os.sep)
        roots = [
            os.path.join(app.root_path, "static", "market_uploads"),
            app.config.get("MEDIA_ROOT", os.path.join(app.root_path, "media")),
            os.path.join(app.root_path, "static"),
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

        low = safe.lower()
        if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
            placeholder_abs = os.path.join(app.root_path, "static", "img", "placeholder_stl.jpg")
            if os.path.isfile(placeholder_abs):
                return send_from_directory(
                    os.path.join(app.root_path, "static", "img"),
                    "placeholder_stl.jpg",
                    mimetype="image/jpeg"
                )

        return abort(404)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

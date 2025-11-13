import os
import threading
import re  # 👈 ДОДАНО
import importlib
import pkgutil

from flask import Flask, render_template, jsonify, request, session, send_from_directory, abort, g
from flask_babel import Babel  # ✅
import stripe  # === (added) Stripe SDK ===

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

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# === BOT FILTER (посилений) ===
BOT_RE = re.compile(
    r"(bot|crawler|spider|ahrefs|semrush|bingpreview|facebookexternalhit|"
    r"twitterbot|slackbot|discordbot|whatsapp|telegrambot|linkedinbot|"
    r"preview|embed|curl|wget|python-requests|node-fetch|axios|postman|"
    r"linkpreview|unfurl|proofly)",
    re.I
)
# НЕ додаємо тут "/api/", бо будемо приймати тільки спец-POST /api/visit
IGNORED_PATHS_PREFIX = ("/static/", "/favicon.ico", "/robots.txt")
IGNORED_PATHS_EXACT = {"/healthz", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"}

def is_bot_ua(ua: str) -> bool:
    if not ua:
        return True
    return bool(BOT_RE.search(ua))

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


# ─────────────────────────────
# worker (опціонально)
# ─────────────────────────────
try:
    from worker import run_worker  # очікуємо функцію run_worker(app)
except Exception:
    run_worker = None


# === MAIN APP CREATOR ===
def create_app():
    app = Flask(__name__)  # ✅ виправлено
    app.secret_key = os.environ.get("SECRET_KEY", "devsecret-change-me")

    # базові Jinja-настройки
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.auto_reload = True

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

    # === Stripe config (added) ===
    app.config["STRIPE_SECRET_KEY"] = os.getenv("STRIPE_SECRET_KEY", "").strip()
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
    if app.config["STRIPE_SECRET_KEY"]:
        stripe.api_key = app.config["STRIPE_SECRET_KEY"]

    @app.context_processor
    def _inject_stripe_keys():
        # даємо доступ до публічного ключа у всіх шаблонах
        return dict(STRIPE_PUBLISHABLE_KEY=app.config.get("STRIPE_PUBLISHABLE_KEY", ""))

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
                # ✅ visits (для метрик)
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS visits (
                      id SERIAL PRIMARY KEY,
                      session_id TEXT NOT NULL,
                      user_id INTEGER,
                      path TEXT,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                """))
                conn.execute(text("""CREATE INDEX IF NOT EXISTS visits_created_idx ON visits (created_at);"""))
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
                # ✅ visits (для метрик)
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS visits (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      session_id TEXT NOT NULL,
                      user_id INTEGER,
                      path TEXT,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                conn.execute(text("""CREATE INDEX IF NOT EXISTS visits_created_idx ON visits (created_at);"""))
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

    # додаткові API-blueprints (якщо існують)
    try:
        import market_api
        app.register_blueprint(market_api.bp, url_prefix="/api/market")
    except Exception as e:
        print("[market_api] skip:", e)

    try:
        import ai_api
        app.register_blueprint(ai_api.bp, url_prefix="/api/ai")
    except Exception as e:
        print("[ai_api] skip:", e)

    try:
        import lang_api
        app.register_blueprint(lang_api.bp, url_prefix="/api/lang")
    except Exception as e:
        print("[lang_api] skip:", e)

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

    # окремо: current_user у g
    @app.before_request
    def _load_current_user():
        g.user = None
        uid = session.get("user_id")
        if uid:
            try:
                g.user = User.query.get(uid)
            except Exception:
                g.user = None

    # === BOT MARKER (не лізе у твої функції підрахунку, лише виставляє прапор) ===
    @app.before_request
    def _mark_bot_and_ignored():
        try:
            path = (request.path or "/")
            if path in IGNORED_PATHS_EXACT or path.startswith(IGNORED_PATHS_PREFIX):
                g.is_bot = True
                return
            ua = request.headers.get("User-Agent", "")
            # боти, прев’юшки месенджерів, сканери
            g.is_bot = is_bot_ua(ua)
        except Exception:
            g.is_bot = False  # безпечний дефолт

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

    @app.context_processor
    def inject_now():
        return dict(now=datetime.utcnow)

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

    # === STL viewer (окреме вікно) ===
    @app.route("/stl/viewer", endpoint="stl_viewer")
    def stl_viewer():
        return render_template("stl_viewer.html")

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

    # --- Допоміжні URL для шаблону admin.html (старі кнопки-заглушки) ---
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
            flash("Дай .png/.jpg/.jpeg/.webп")
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

    # === ⬇️ НОВЕ: Reset visits ===
    @app.route("/admin/reset-visits", methods=["POST"])
    @admin_required
    def admin_reset_visits():
        """
        Очищає всю таблицю visits (метрики "онлайн" і "унікальних за місяць" почнуть рахуватись з нуля).
        """
        try:
            db.session.execute(text("DELETE FROM visits;"))
            db.session.commit()
            from flask import flash, redirect, url_for
            flash("Логи відвідувань очищено.")
            return redirect(url_for("admin_panel"))
        except Exception as e:
            db.session.rollback()
            from flask import flash, redirect, url_for
            flash(f"Не вдалось очистити visits: {e}")
            return redirect(url_for("admin_panel"))

    # === ⬇️ lightweight visits tracker — тепер лише для людських JS-сигналів
    from time import time as _now

    @app.before_request
    def _track_visit():
        try:
            # ✅ Рахуємо тільки спеціальний POST із фронтенда
            if request.method != "POST" or request.path != "/api/visit":
                return

            # хедер-маячок, щоб сторонні POST не засмічували метрику
            if request.headers.get("X-Visit-Beacon") != "1":
                return ("", 204)

            # відсікаємо боти / службові
            if getattr(g, "is_bot", False):
                return ("", 204)

            # шлях беремо з JSON-тела
            data = request.get_json(silent=True) or {}
            path = (data.get("path") or "/")[:255]
            if path in IGNORED_PATHS_EXACT or path.startswith(IGNORED_PATHS_PREFIX):
                return ("", 204)

            # сесія
            sid = session.get("sid")
            if not sid:
                sid = os.urandom(16).hex()
                session["sid"] = sid

            # анти-спам: не частіше ніж раз/хвилину
            last_ts = session.get("_last_visit_ts") or 0
            if _now() - float(last_ts) < 60:
                return ("", 204)
            session["_last_visit_ts"] = _now()

            uid = session.get("user_id")

            # INSERT без created_at — візьметься дефолт БД (NOW()/CURRENT_TIMESTAMP)
            db.session.execute(
                text("INSERT INTO visits (session_id, user_id, path) VALUES (:sid, :uid, :pth)"),
                {"sid": sid, "uid": uid, "pth": path}
            )
            db.session.commit()
            return ("", 204)
        except Exception:
            db.session.rollback()
            return ("", 204)

    # === Healthcheck ===
    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/health")
    def health():
        return "ok", 200

    # === Robots (щоб чемні боти поважали) ===
    @app.route("/robots.txt")
    def robots_txt():
        try:
            return send_from_directory(os.path.join(app.root_path, "static"), "robots.txt")
        except Exception:
            return ("User-agent: *\nCrawl-delay: 5\n", 200, {"Content-Type": "text/plain; charset=utf-8"})

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

    # простий route для локальних uploads (якщо треба окремо від media)
    @app.route("/uploads/<path:filename>")
    def uploads(filename):
        upload_root = os.path.join(app.root_path, "uploads")
        safe = os.path.normpath(filename).lstrip(os.sep)
        full = os.path.join(upload_root, safe)
        if not os.path.isfile(full):
            abort(404)
        return send_from_directory(upload_root, safe)

    # === (added) Stripe routes for card payments ===
    @app.route("/donate")
    def donate_page():
        return render_template("donate.html")

    @app.post("/create-payment-intent")
    def create_payment_intent():
        if not app.config.get("STRIPE_SECRET_KEY"):
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
                description="Proofly Balance Top-Up (card)"
            )
            return jsonify(clientSecret=intent.client_secret)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/success")
    def success_page():
        return render_template("success.html") if os.path.exists(
            os.path.join(app.root_path, "templates", "success.html")
        ) else ("<h2 style='color:#16a34a'>✅ Оплата успішна</h2>", 200)

    # ─────────────────────────────
    # автопідключення api_routes/*
    # ─────────────────────────────
    try:
        register_api_routes(app)
    except Exception as e:
        print("[api_routes] skipped:", e)

    # ─────────────────────────────
    # запуск background worker
    # ─────────────────────────────
    if app.config.get("ENABLE_WORKER", True) and run_worker is not None:
        start_worker_thread(app)

    return app


# ─────────────────────────────
# helper-функції ПІСЛЯ create_app
# (будуть визначені до виклику create_app)
# ─────────────────────────────
def register_api_routes(app):
    """
    Шукає всі .py файли в папці api_routes
    і, якщо в модулі є змінна bp (Blueprint), реєструє її як /api/<ім'я>.
    """
    package_name = "api_routes"
    package_path = os.path.join(BASE_DIR, "api_routes")
    if not os.path.isdir(package_path):
        return

    for _, module_name, ispkg in pkgutil.iter_modules([package_path]):
        if ispkg or module_name.startswith("_"):
            continue
        full_module_name = f"{package_name}.{module_name}"
        try:
            module = importlib.import_module(full_module_name)
        except Exception as e:
            print(f"[api_routes] import fail {full_module_name}: {e}")
            continue

        bp = getattr(module, "bp", None) or getattr(module, "blueprint", None)
        if bp is None:
            continue

        url_prefix = "/api/" + module_name.replace("_api", "")
        try:
            app.register_blueprint(bp, url_prefix=url_prefix)
            print(f"[api_routes] registered {full_module_name} at {url_prefix}")
        except Exception as e:
            print(f"[api_routes] register fail {full_module_name}: {e}")


def start_worker_thread(app):
    """Запускає фоновий воркер у окремому потоці."""
    if run_worker is None:
        return

    def _run():
        with app.app_context():
            try:
                run_worker(app)
            except Exception as e:
                print("[worker] stopped:", e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

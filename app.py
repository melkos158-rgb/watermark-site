import logging
import os
import re
import threading
from collections import deque
from datetime import datetime
from functools import wraps

# ...existing code...
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    dsn = os.environ.get("SENTRY_DSN")
    if dsn:
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        )
except ImportError:
    pass
# --- structlog setup for structured logging ---
try:
    import structlog
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )
    log = structlog.get_logger()
except ImportError:
    log = None
run_worker = None
try:
    from rich.traceback import install
    install(show_locals=True)
except ImportError:
    pass

try:
    import better_exceptions
    better_exceptions.hook()
except ImportError:
    pass
import os

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session)
from sqlalchemy import text

from ads import bp as ads_bp
from db import close_db, init_app_db
from dev_bp import dev_bp

# Optional deps (don’t crash app if not installed/disabled)
try:
    from flask_babel import Babel
except Exception:  # pragma: no cover
    Babel = None

try:
    import stripe
except Exception:  # pragma: no cover
    stripe = None

# Project deps
from models import \
    db as models_db  # keep this import if models.py defines `db`

db = models_db  # alias used throughout app.py

# === ADMIN CONFIG ===
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
}

USERS_TBL = "users"
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# === BOT FILTER (посилений) ===
BOT_RE = re.compile(
    r"(bot|crawler|spider|ahrefs|semrush|bingpreview|facebookexternalhit|"
    r"twitterbot|slackbot|discordbot|whatsapp|telegrambot|linkedinbot|"
    r"preview|embed|curl|wget|python-requests|node-fetch|axios|postman|"
    r"linkpreview|unfurl|proofly)",
    re.I,
)
IGNORED_PATHS_PREFIX = ("/static/", "/favicon.ico", "/robots.txt")
IGNORED_PATHS_EXACT = {
    "/healthz",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
}


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


def admin_required(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("is_admin"):
            from flask import flash, redirect, url_for
            flash("Доступ лише для адміністратора.")
            return redirect(url_for("core.index"))
        return f(*args, **kwargs)
    return _wrap


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


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "devsecret-change-me")

    # --- Safe URL helper for templates ---
    def safe_url_for(endpoint, **values):
        from flask import current_app, url_for
        if endpoint in current_app.view_functions:
            try:
                return url_for(endpoint, **values)
            except Exception:
                return None
        return None
    app.jinja_env.globals["safe_url_for"] = safe_url_for

    import uuid
    from flask import render_template, g, request

    @app.before_request
    def assign_request_id():
        g.request_id = str(uuid.uuid4())

    @app.errorhandler(404)
    def handle_404(e):
        rid = getattr(g, 'request_id', None) or str(uuid.uuid4())
        return render_template("errors/404.html", request_id=rid), 404

    @app.errorhandler(500)
    def handle_500(e):
        rid = getattr(g, 'request_id', None) or str(uuid.uuid4())
        return render_template("errors/500.html", request_id=rid), 500

    # Explicitly import and assign blueprints
    import core_pages
    core_bp = core_pages.bp
    import profile
    profile_bp = profile.bp
    import market
    market_bp = market.bp

    # Lightweight in-memory error collector
    app.config["DEBUG_ERRORS"] = deque(maxlen=200)
    app.config["DEBUG_BP_STATUS"] = {}
    app.config["DEBUG_IMPORT_ERRORS"] = {}

    class DebugErrorHandler(logging.Handler):
        def emit(self, record):
            entry = {
                "ts": datetime.utcnow().isoformat() + 'Z',
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            if record.exc_info:
                import traceback as _traceback
                entry["trace"] = ''.join(_traceback.format_exception(*record.exc_info))
            app.config.setdefault("DEBUG_ERRORS", []).append(entry)

    debug_handler = DebugErrorHandler()
    debug_handler.setLevel(logging.ERROR)
    app.logger.addHandler(debug_handler)
    logging.getLogger().addHandler(debug_handler)

    def register_bp(name, import_func, attr="bp", url_prefix=None):
        try:
            mod = import_func()
            bp = getattr(mod, attr, None)
            if bp is None:
                print(f"[{name}] skip: module has no attribute '{attr}'")
                return
            if url_prefix:
                app.register_blueprint(bp, url_prefix=url_prefix)
            else:
                app.register_blueprint(bp)
            app.config["DEBUG_BP_STATUS"][name] = True
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app.config["DEBUG_BP_STATUS"][name] = False
            app.config["DEBUG_IMPORT_ERRORS"][name] = tb
            app.config["DEBUG_ERRORS"].append({
                "ts": datetime.utcnow().isoformat() + 'Z',
                "level": "ERROR",
                "logger": f"register_bp.{name}",
                "msg": str(e),
                "trace": tb,
            })

    # Register blueprints using helper (no duplicates)
    register_bp("debug_admin", lambda: __import__("debug_admin"))
    register_bp("ai_api", lambda: __import__("ai_api"))
    register_bp("market_api", lambda: __import__("market_api"), url_prefix="/api/market")
    register_bp("lang_api", lambda: __import__("lang_api"), url_prefix="/api/lang")
    app.register_blueprint(core_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(market_bp)


    # ...existing code...

    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024

    # 📦 ASSET VERSION - кеш-бастінг для CSS/JS
    app.config["ASSET_V"] = (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT")
        or os.getenv("RENDER_GIT_COMMIT")
        or "dev"
    )

    # === Production marker route for deployment verification ===
    @app.get("/__prod_marker")
    def __prod_marker():
        return {"ok": True, "ts": "2025-12-20", "file": __file__}

    @app.context_processor
    def inject_asset_v():
        # Inject asset_v into all templates for cache busting
        return {"asset_v": app.config["ASSET_V"]}


    # ========= i18n =========
    if Babel is not None:
        babel = Babel()

        def _get_locale():
            lang = None
            if session.get("user_id"):
                try:
                    from models import User
                    u = User.query.get(session["user_id"])
                    if u and hasattr(u, "lang") and u.lang:
                        lang = (u.lang or "").lower()
                except Exception:
                    pass
            if not lang:
                lang = (session.get("lang") or "uk").lower()
            return (lang[:8] or "uk")

        babel.init_app(app, locale_selector=_get_locale)

        @app.context_processor
        def _inject_current_lang():
            try:
                cur = _get_locale()
            except Exception:
                cur = (session.get("lang") or "uk")
            return dict(current_lang=cur)

    # ========= шляхи для файлів =========
    base_dir = os.path.abspath(os.path.dirname(__file__))

    # ✅ ВАЖЛИВО: UPLOADS_ROOT з ENV має пріоритет (Railway volume /data/market_uploads)
    uploads_root_env = os.getenv("UPLOADS_ROOT", "").strip()
    uploads_root = uploads_root_env or os.path.join(base_dir, "market_uploads")
    app.config["UPLOADS_ROOT"] = uploads_root
    os.makedirs(uploads_root, exist_ok=True)

    # ✅ ФІКС: /media/* повинно читати з того ж місця, куди ти зберігаєш нові аплоади
    # (інакше нові файли лежать у volume, а /media шукає у /app/media -> 404)
    app.config["MEDIA_ROOT"] = uploads_root
    app.config.setdefault("MEDIA_URL", "/media/")
    os.makedirs(app.config["MEDIA_ROOT"], exist_ok=True)

    # (legacy) static/market_uploads існування залишаємо
    legacy_static_uploads = os.path.join(app.root_path, "static", "market_uploads")
    os.makedirs(legacy_static_uploads, exist_ok=True)

    # ========= STRIPE =========

    app.config["STRIPE_SECRET_KEY"] = os.getenv("STRIPE_SECRET_KEY", "").strip()
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
    if stripe is not None and app.config["STRIPE_SECRET_KEY"]:
        stripe.api_key = app.config["STRIPE_SECRET_KEY"]

    @app.context_processor
    def _inject_stripe_keys():
        return dict(STRIPE_PUBLISHABLE_KEY=app.config.get("STRIPE_PUBLISHABLE_KEY", ""))

    # ========= БД =========
    init_app_db(app)
    app.teardown_appcontext(close_db)
    models_db.init_app(app)

    # === STL Market: створити таблиці market_* якщо їх ще немає ===
    try:
        import models_market  # noqa: F401
        with app.app_context():
            db.create_all()
    except Exception as e:
        print("[models_market] skip:", e)

    # ========= разове створення службових таблиць =========
    _tables_ready_key = "FEEDBACK_TABLES_READY"
    _tables_lock = threading.Lock()
    app.config.setdefault(_tables_ready_key, False)

    def ensure_feedback_tables():
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
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS visits (
                      id SERIAL PRIMARY KEY,
                      session_id TEXT NOT NULL,
                      user_id INTEGER,
                      path TEXT,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS visits_created_idx ON visits (created_at);"))
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
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS visits (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      session_id TEXT NOT NULL,
                      user_id INTEGER,
                      path TEXT,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS visits_created_idx ON visits (created_at);"))
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

    # ========= CACHE HEADERS FOR STATIC FILES =========
    @app.after_request
    def add_static_cache_headers(resp):
        path = request.path or ""
        if path.startswith("/static/vendor/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/static/") and (path.endswith(".css") or path.endswith(".js") or path.endswith(".woff2")):
            resp.headers["Cache-Control"] = "public, max-age=604800"
        return resp

    # ========= реєстрація blueprints =========

    import auth
    import chat

    try:
        import market
    except Exception as e:
        import traceback
        print("❌ [market] skipped due to import error:", e)
        traceback.print_exc()

    app.register_blueprint(auth.bp)
    app.register_blueprint(chat.bp)

    app.register_blueprint(ads_bp)
    app.register_blueprint(dev_bp)

    # окремі API-blueprints

    # --- market_api ---
    try:
        import market_api
        if "market_api" not in app.blueprints:
            app.register_blueprint(market_api.bp, url_prefix="/api/market")
            app.logger.warning("✅ market_api.bp registered with /api/market")
        else:
            app.logger.warning("⚠️ market_api already registered — skip")
    except Exception:
        app.logger.exception("❌ [market_api] FAILED to register")

    # --- HARD compat endpoints (app-level, bypass blueprints) ---

    @app.get("/api/market/ping")
    def api_market_ping_app():
        try:
            import ai_api
            app.register_blueprint(ai_api.bp, url_prefix="/api/ai")
            print("✅ [ai_api] registered at /api/ai")
        except Exception as e:
            print(f"⚠️ [ai_api] skip: {e}")



    # --- COMPAT: /api/my/items for legacy frontend ---
    @app.get("/api/my/items")
    def compat_api_my_items():
        from flask import request

        # Proxy to /api/market/my/items with query string
        qs = request.query_string.decode()
        url = "/api/market/my/items"
        if qs:
            url += f"?{qs}"
        return redirect(url, code=307)

    # --- end compat endpoints ---

    try:
        import ai_api
        app.register_blueprint(ai_api.bp, url_prefix="/api/ai")
        print("✅ [ai_api] registered at /api/ai")
    except Exception as e:
        print(f"⚠️ [ai_api] skip: {e}")

    # --- lang_api ---
    # --- lang_api ---
    try:
        import lang_api
        if "lang_api" not in app.blueprints:
            app.register_blueprint(lang_api.bp, url_prefix="/api/lang")
            app.logger.warning("✅ lang_api.bp registered with /api/lang")
        else:
            app.logger.warning("⚠️ lang_api already registered — skip")
    except Exception:
        app.logger.exception("⚠️ [lang_api] skip")

    # ========= before_request хуки =========
    from flask import session  # якщо ще нема

    # ADMIN_EMAILS має бути визначений вище
    @app.before_request
    def _mark_admin():
        uid = session.get("user_id")
        if not uid:
            session.pop("is_admin", None)
            return
        try:
            from models import User  # lazy + safe
            u = User.query.get(uid)
        except Exception:
            # не валимо весь сайт через адмін-прапорець
            session.pop("is_admin", None)
            return
        if u and getattr(u, "email", None) and u.email.lower() in ADMIN_EMAILS:
            session["is_admin"] = True
        else:
            session.pop("is_admin", None)

    @app.before_request
    def _load_current_user():
        g.user = None
        uid = session.get("user_id")
        if uid:
            try:
                from models import User
                g.user = User.query.get(uid)
            except Exception:
                g.user = None

    @app.before_request
    def _mark_bot_and_ignored():
        try:
            path = (request.path or "/")
            if path in IGNORED_PATHS_EXACT or path.startswith(IGNORED_PATHS_PREFIX):
                g.is_bot = True
                return
            ua = request.headers.get("User-Agent", "")
            g.is_bot = is_bot_ua(ua)
        except Exception:
            g.is_bot = False

    # ========= контекстні процесори =========
    @app.context_processor
    def inject_user():
        from models import User
        u = User.query.get(session["user_id"]) if session.get("user_id") else None
        return dict(current_user=u, pxp=(to_int(u.pxp) if u else 0))

    @app.context_processor
    def _inject_admin_metrics():
        try:
            total_users = db.session.execute(text(f"SELECT COUNT(*) FROM {USERS_TBL}")).scalar() or 0

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
            return dict(admin_metrics={
                "total_users": 0,
                "online_now": 0,
                "monthly_visitors": 0,
            })


    # ========= адмін-панель =========
    @app.route("/admin", endpoint="admin_panel")
    @admin_required
    def admin_panel():
        return render_template("admin.html")

    app.add_url_rule("/admin/reset-month", endpoint="admin_reset_month", view_func=admin_panel, methods=["POST"])
    app.add_url_rule("/admin/pxp-add", endpoint="admin_pxp_add", view_func=admin_panel, methods=["POST"])

    @app.route("/admin/reset-visits", methods=["POST"])
    @admin_required
    def admin_reset_visits():
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

    # ========= трекінг візитів (API) =========
    from time import time as _now

    @app.before_request
    def _track_visit():
        try:
            if request.method != "POST" or request.path != "/api/visit":
                return
            if request.headers.get("X-Visit-Beacon") != "1":
                return ("", 204)
            if getattr(g, "is_bot", False):
                return ("", 204)

            data = request.get_json(silent=True) or {}
            path = (data.get("path") or "/")[:255]
            if path in IGNORED_PATHS_EXACT or path.startswith(IGNORED_PATHS_PREFIX):
                return ("", 204)

            sid = session.get("sid")
            if not sid:
                sid = os.urandom(16).hex()
                session["sid"] = sid

            last_ts = session.get("_last_visit_ts") or 0
            if _now() - float(last_ts) < 60:
                return ("", 204)
            session["_last_visit_ts"] = _now()

            uid = session.get("user_id")
            db.session.execute(
                text("INSERT INTO visits (session_id, user_id, path) VALUES (:sid, :uid, :pth)"),
                {"sid": sid, "uid": uid, "pth": path},
            )
            db.session.commit()
            return ("", 204)
        except Exception:
            db.session.rollback()
            return ("", 204)

    # ========= health =========
    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/health")
    def health():
        return "ok", 200

    # ========= auto-реєстрація модулів з api_routes/* =========
    # (No dynamic loader implemented; skip if not needed)

    # ========= background-worker =========
    if app.config.get("ENABLE_WORKER", True) and run_worker is not None:
        start_worker_thread(app)


    try:
        import ai_api
        app.register_blueprint(ai_api.bp, url_prefix="/api/ai")
        print("✅ [ai_api] registered at /api/ai")
    except Exception as e:
        print(f"⚠️ [ai_api] skip: {e}")

    return app


def start_worker_thread(app):
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




if __name__ == "__main__":
    app = create_app()
    if app is None:
        raise RuntimeError("create_app() returned None (startup failed)")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

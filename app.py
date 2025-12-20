import os
import threading
import re
import importlib
import pkgutil

from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    session,
    send_from_directory,
    abort,
    g,
)
from flask_babel import Babel
import stripe

from db import init_app_db, close_db, db, User
from models import db as models_db, MarketItem  # MarketItem може знадобитись далі

from functools import wraps
from sqlalchemy import text

# blueprints з окремих модулів
from core_pages import bp as core_bp      # 🌟 головні сторінки, /media, /donate, /lang…
from ads import bp as ads_bp              # 🌟 банер TOP-1 і /ad/*
from dev_bp import dev_bp                 # 🌟 dev-інструменти (/admin/dev-issues, /admin/dev-map)

# === worker (опціонально) ===
try:
    from worker import run_worker  # очікуємо def run_worker(app): ...
except Exception:
    run_worker = None

# === ADMIN CONFIG ===
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
}

USERS_TBL = getattr(User, "__tablename__", "users") or "users"
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
            from flask import redirect, url_for, flash
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

    # === Temporary endpoint to list all real routes (for diagnostics) ===
    @app.get("/__routes")
    def __routes():
        rules = []
        for r in app.url_map.iter_rules():
            rules.append({
                "rule": str(r),
                "methods": sorted([m for m in r.methods if m not in ("HEAD", "OPTIONS")]),
                "endpoint": r.endpoint,
            })
        # Show only those related to api/market
        filtered = [x for x in rules if "/api/market" in x["rule"] or "market_api" in x["endpoint"]]
        return {"count": len(filtered), "routes": filtered}

    # 🔧 максимальний розмір запиту (щоб великий upload не рвав конект)
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
        """Віддає asset_v в усі шаблони для ?v=commit_hash"""
        return {"asset_v": app.config["ASSET_V"]}

    # ========= i18n =========
    babel = Babel()

    def _get_locale():
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
    if app.config["STRIPE_SECRET_KEY"]:
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
    import auth, profile, chat, market

    app.register_blueprint(auth.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(chat.bp)
    app.register_blueprint(market.bp)

    app.register_blueprint(core_bp)
    app.register_blueprint(ads_bp)
    app.register_blueprint(dev_bp)

    # окремі API-blueprints

    try:
        import market_api
        app.register_blueprint(market_api.bp, url_prefix="/api/market")
        app.logger.warning("✅ market_api.bp registered with /api/market")
        print("✅ [market_api] registered at /api/market")
    except Exception as e:
        print(f"❌ [market_api] FAILED to register: {e}")
        import traceback
        traceback.print_exc()

    # --- HARD compat endpoints (app-level, bypass blueprints) ---
    @app.get("/api/market/ping")
    def api_market_ping_app():
        return jsonify(
            ok=True,
            route="/api/market/ping",
            file=__file__,
            commit=os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or "unknown",
        ), 200

    @app.post("/_debug/api/market/items/draft")
    def api_market_items_draft_app():
        # Minimal response for debug, no longer conflicts with blueprint.
        return jsonify(
            ok=True,
            route="/_debug/api/market/items/draft",
            draft=True,
            file=__file__,
            commit=os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or "unknown",
            content_type=request.content_type,
        ), 200
    # --- end compat endpoints ---

    try:
        import ai_api
        app.register_blueprint(ai_api.bp, url_prefix="/api/ai")
        print("✅ [ai_api] registered at /api/ai")
    except Exception as e:
        print(f"⚠️ [ai_api] skip: {e}")

    try:
        import lang_api
        app.register_blueprint(lang_api.bp, url_prefix="/api/lang")
        print("✅ [lang_api] registered at /api/lang")
    except Exception as e:
        print(f"⚠️ [lang_api] skip: {e}")

    # ========= before_request хуки =========
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

    @app.before_request
    def _load_current_user():
        g.user = None
        uid = session.get("user_id")
        if uid:
            try:
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
    try:
        register_api_routes(app)
    except Exception as e:
        print("[api_routes] skipped:", e)

    # ========= background-worker =========
    if app.config.get("ENABLE_WORKER", True) and run_worker is not None:
        start_worker_thread(app)

    return app


def register_api_routes(app):
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

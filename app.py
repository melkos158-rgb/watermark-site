import os
import threading
from flask import Flask, render_template, jsonify, request, session, send_from_directory, abort  # +send_from_directory, abort

from db import init_app_db, close_db, db, User  # підключаємо БД тут
# >>> ДОДАНО: підключаємо моделі з models.py і ініціалізуємо їх db
from models import db as models_db, MarketItem

# === NEW: налаштування адміна та банера ===
from functools import wraps
from datetime import datetime
from werkzeug.utils import secure_filename

# NEW: для сирих SQL і перехоплення унікальних вставок
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
UPLOAD_DIR = os.path.join("static", "ads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}

DEFAULT_BANNER_IMG = os.getenv("DEFAULT_BANNER_IMG", "ads/default_banner.jpg")  # поклади свій файл у static/ads/
DEFAULT_BANNER_URL = os.getenv("DEFAULT_BANNER_URL", "")  # опційно

# назва таблиці користувачів для JOIN
USERS_TBL = getattr(User, "__tablename__", "users") or "users"

# ---- helper: безпечно приводимо до int ----
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
        from flask import session, redirect, url_for, flash
        if not session.get("is_admin"):
            flash("Доступ лише для адміністратора.")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return _wrap


# === NEW: моделі для банера (простенько в цьому файлі) ===
class BannerAd(db.Model):
    __tablename__ = "banner_ad"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)   # хто завантажив (ТОП-1)
    image_path = db.Column(db.String(255), nullable=False)  # шлях усередині static/ (наприклад "ads/xxx.jpg")
    link_url = db.Column(db.String(500))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ====== NEW: хелпери для JSON-API чату покращень ======
def login_required_json(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"ok": False, "error": "auth_required"}), 401
        return f(*args, **kwargs)
    return inner

def row_to_dict(row):
    # SQLAlchemy Row -> dict
    try:
        return dict(row._mapping)
    except Exception:
        return dict(row)

# =======================================================


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "devsecret-change-me")

    # --- ДОДАНО: конфіг медіа та створення директорії ---
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app.config.setdefault("MEDIA_ROOT", os.path.join(base_dir, "media"))
    app.config.setdefault("MEDIA_URL", "/media/")
    os.makedirs(app.config["MEDIA_ROOT"], exist_ok=True)
    # -----------------------------------------------------

    # 1) підключаємо БД до Flask
    init_app_db(app)
    app.teardown_appcontext(close_db)

    # >>> ДОДАНО: ініціалізуємо db із models.py (MarketItem)
    models_db.init_app(app)

    # --- NEW: гарантуємо наявність таблиць (з урахуванням ринку) ---
    _tables_ready_key = "FEEDBACK_TABLES_READY"
    _tables_lock = threading.Lock()
    app.config.setdefault(_tables_ready_key, False)

    def ensure_feedback_tables():
        """Створює/оновлює таблиці. Працює для PostgreSQL та SQLite.
           ВАЖЛИВО: таблиця items містить format, rating, downloads.
        """
        dialect = db.engine.dialect.name  # 'postgresql' | 'sqlite' | ін.
        with db.engine.begin() as conn:   # автокоміт DDL
            if dialect == "postgresql":
                # --- існуючі ---
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
                # --- банери ---
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
                # --- ринок (нова схема) ---
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
                # на всяк випадок — догонимо колонки, якщо таблиця стара
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS "description" TEXT DEFAULT ''"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS cover_url TEXT"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS gallery_urls TEXT DEFAULT '[]'"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS stl_main_url TEXT"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS stl_extra_urls TEXT DEFAULT '[]'"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS zip_url TEXT"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS format VARCHAR(16) DEFAULT 'stl'"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS rating DOUBLE PRECISION DEFAULT 0"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS downloads INTEGER DEFAULT 0"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()"""))
                conn.execute(text("""ALTER TABLE items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()"""))

                # >>> FIX: додаємо відсутню колонку users.avatar_url (щоб не падало при SELECT)
                conn.execute(text("""ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT"""))

            else:
                # --- існуючі ---
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
                    CREATE TABLE IF NOT EXISTS suggestion_votes (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      suggestion_id INTEGER NOT NULL,
                      user_id INTEGER NOT NULL,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      UNIQUE(suggestion_id, user_id)
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS suggestion_comments (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      suggestion_id INTEGER NOT NULL,
                      user_id INTEGER NOT NULL,
                      body TEXT NOT NULL,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS pxp_transactions (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      delta INTEGER NOT NULL,
                      reason TEXT NOT NULL,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                # --- банери ---
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
                # --- ринок (нова схема) ---
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
                # доганяємо відсутні колонки (SQLite не має IF NOT EXISTS для ADD COLUMN у старих версіях — ловимо помилки)
                for ddl in [
                    """ALTER TABLE items ADD COLUMN "description" TEXT DEFAULT ''""",
                    """ALTER TABLE items ADD COLUMN cover_url TEXT""",
                    """ALTER TABLE items ADD COLUMN gallery_urls TEXT DEFAULT '[]'""",
                    """ALTER TABLE items ADD COLUMN stl_main_url TEXT""",
                    """ALTER TABLE items ADD COLUMN stl_extra_urls TEXT DEFAULT '[]'""",
                    """ALTER TABLE items ADD COLUMN zip_url TEXT""",
                    """ALTER TABLE items ADD COLUMN format TEXT DEFAULT 'stl'""",
                    """ALTER TABLE items ADD COLUMN rating REAL DEFAULT 0""",
                    """ALTER TABLE items ADD COLUMN downloads INTEGER DEFAULT 0""",
                    """ALTER TABLE items ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP""",
                    """ALTER TABLE items ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP""",
                ]:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        pass  # вже є — ок

                # >>> FIX: додаємо колонку users.avatar_url для SQLite (ігноруємо помилку, якщо вже існує)
                try:
                    conn.execute(text("""ALTER TABLE users ADD COLUMN avatar_url TEXT"""))
                except Exception:
                    pass

    # одноразовий виклик на першому запиті (Flask 3: before_first_request відсутній)
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
    # ----------------------------------------------------------------------

    # 2) тільки після ініціалізації БД — імпорт і реєстрація blueprints
    import auth
    import profile
    import chat
    import market
    app.register_blueprint(auth.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(chat.bp)
    app.register_blueprint(market.bp)

    # === NEW: before_request — відмічаємо адміна за email із ENV ===
    @app.before_request
    def _mark_admin():
        from flask import session
        uid = session.get("user_id")
        if not uid:
            session.pop("is_admin", None)
            return
        u = User.query.get(uid)
        if u and u.email and u.email.lower() in ADMIN_EMAILS:
            session["is_admin"] = True
        else:
            session.pop("is_admin", None)

    # === NEW: утиліти для TOP-1 і банера ===
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

    # 3) доступні у всіх шаблонах
    @app.context_processor
    def inject_user():
        from flask import session
        u = User.query.get(session["user_id"]) if session.get("user_id") else None
        return dict(current_user=u, pxp=(to_int(u.pxp) if u else 0))

    @app.context_processor
    def inject_banner():
        return dict(banner=get_active_banner())

    # ===== ПУБЛІЧНІ СТОРІНКИ =====
    @app.route("/", endpoint="index")  # >>> FIX: явно фіксуємо ім'я ендпоінта
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

    # --- ДОДАНО: сторінка фільтрів (щоб <iframe src="filters.html"> не давала 404) ---
    @app.route("/filters")
    @app.route("/filters.html")
    def filters_page():
        return render_template("filters.html")
    # ----------------------------------------------------------------------------------

    @app.route("/photo")
    def photo():
        return render_template("photo.html")

    # --- ДОДАНО: сторінка документів (Documents) ---
    @app.route("/documents")
    @app.route("/documents.html")
    def documents():
        return render_template("documents.html")
    # -----------------------------------------------

    @app.route("/ad/click")
    def ad_click():
        from flask import session, redirect, url_for, request
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        b = get_active_banner()
        if b.get("link_url"):
            return redirect(b["link_url"])
        return redirect(url_for("index"))

    @app.route("/ad/upload", methods=["GET", "POST"])
    def ad_upload():
        from flask import request, session, redirect, url_for, flash, render_template
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

    @app.route("/admin", endpoint="admin_panel")  # >>> FIX: явно фіксуємо ім'я ендпоінта
    @admin_required
    def admin_panel():
        return render_template("admin.html")

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
        fname = f"default_banner.{ext}"""
        save_rel = os.path.join("ads", fname).replace("\\", "/")
        save_abs = os.path.join("static", save_rel)
        os.makedirs(os.path.dirname(save_abs), exist_ok=True)
        f.save(save_abs)

        global DEFAULT_BANNER_IMG, DEFAULT_BANNER_URL
        DEFAULT_BANNER_IMG = save_rel
        DEFAULT_BANNER_URL = link_url

        flash("Дефолтний банер оновлено.")
        return redirect(url_for("admin_panel"))

    @app.route("/admin/reset-month", methods=["POST"])
    @admin_required
    def admin_reset_month():
        changed = False
        if hasattr(User, "pxp_month"):
            for u in User.query.all():
                try:
                    u.pxp_month = int(u.pxp_month or 0)
                except Exception:
                    u.pxp_month = 0
                u.pxp_month = 0
                changed = True
        BannerAd.query.filter_by(active=True).update({"active": False})
        db.session.commit()
        from flask import redirect, url_for, flash
        flash("Місячний рейтинг скинуто. Повернувся дефолтний банер.")
        return redirect(url_for("admin_panel"))

    @app.route("/admin/pxp-add", methods=["POST"])
    @admin_required
    def admin_pxp_add():
        from flask import request, redirect, url_for, flash

        def _to_int(v):
            try:
                return int(v)
            except Exception:
                return 0

        email = (request.form.get("email") or "").strip().lower()
        amount_raw = request.form.get("amount") or "0"
        add_total = "add_total" in request.form
        add_month = "add_month" in request.form

        try:
            amount = int(amount_raw)
        except Exception:
            amount = 0

        if not email or amount <= 0:
            flash("Вкажи коректні email та додатне число PXP.")
            return redirect(url_for("admin_panel"))

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if not user:
            flash(f"Користувача з email {email} не знайдено.")
            return redirect(url_for("admin_panel"))

        if add_total and hasattr(User, "pxp"):
            user.pxp = _to_int(user.pxp) + amount

        if add_month and hasattr(User, "pxp_month"):
            user.pxp_month = _to_int(user.pxp_month) + amount

        db.session.commit()

        where = []
        if add_total and hasattr(User, "pxp"): where.append("загальний")
        if add_month and hasattr(User, "pxp_month"): where.append("місячний")
        where_str = " і ".join(where) if where else "—"
        flash(f"Нараховано +{amount} PXP користувачу {user.email} ({where_str}).")
        return redirect(url_for("admin_panel"))

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    # ======================================================================
    # ================== NEW: API для "чату покращень" ======================
    # ======================================================================

    @app.route("/api/suggestions")
    def api_suggestions_list():
        rows = db.session.execute(text(f"""
            SELECT s.*, u.name AS author_name, u.email AS author_email
            FROM suggestions s
            JOIN {USERS_TBL} u ON u.id = s.user_id
            ORDER BY s.likes DESC, s.created_at DESC
            LIMIT 100
        """)).fetchall()
        return jsonify({"ok": True, "items": [row_to_dict(r) for r in rows]})

    @app.route("/api/suggestions", methods=["POST"])
    @login_required_json
    def api_suggestions_create():
        uid = session["user_id"]
        data = request.get_json() or {}
        text_body = (data.get("title") or data.get("body") or "").strip()
        if not text_body:
            return jsonify({"ok": False, "error": "title_required"}), 400

        try:
            user = User.query.get(uid)
            if not user:
                return jsonify({"ok": False, "error": "no_user"}), 400

            pxp_val = to_int(getattr(user, "pxp", 0))
            if pxp_val < 1:
                return jsonify({"ok": False, "error": "not_enough_pxp"}), 402

            user.pxp = pxp_val - 1

            engine = db.session.get_bind().dialect.name
            if engine == "postgresql":
                sid = db.session.execute(
                    text("INSERT INTO suggestions(user_id, title, body) VALUES(:uid, :t, '') RETURNING id"),
                    {"uid": uid, "t": text_body}
                ).scalar()
            else:
                db.session.execute(
                    text("INSERT INTO suggestions(user_id, title, body) VALUES(:uid, :t, '')"),
                    {"uid": uid, "t": text_body}
                )
                sid = db.session.execute(text("SELECT last_insert_rowid()")).scalar()

            db.session.execute(
                text("INSERT INTO pxp_transactions(user_id, delta, reason) VALUES(:uid, -1, 'suggestion_post')"),
                {"uid": uid}
            )
            db.session.commit()

            row = db.session.execute(text(f"""
                SELECT s.*, u.name AS author_name, u.email AS author_email
                FROM suggestions s
                JOIN {USERS_TBL} u ON u.id = s.user_id
                WHERE s.id = :sid
            """), {"sid": sid}).fetchone()

            return jsonify({"ok": True, "item": dict(row._mapping)})

        except Exception as e:
            db.session.rollback()
            return jsonify({"ok": False, "error": "server", "detail": str(e)}), 500

    @app.route("/api/suggestions/<int:sid>/like", methods=["POST"])
    @login_required_json
    def api_suggestions_like(sid):
        uid = session["user_id"]
        try:
            db.session.execute(text("""
                INSERT INTO suggestion_votes(suggestion_id, user_id)
                VALUES(:sid, :uid)
            """), {"sid": sid, "uid": uid})
            db.session.execute(text("""
                UPDATE suggestions SET likes = likes + 1 WHERE id=:sid
            """), {"sid": sid})
            db.session.commit()
            return jsonify({"ok": True})
        except IntegrityError:
            db.session.rollback()
            return jsonify({"ok": False, "error": "already_voted"}), 409

    @app.route("/api/suggestions/<int:sid>/comments")
    def api_suggestions_comments_list(sid):
        rows = db.session.execute(text(f"""
            SELECT c.*, u.name AS author_name, u.email AS author_email
            FROM suggestion_comments c
            JOIN {USERS_TBL} u ON u.id=c.user_id
            WHERE c.suggestion_id=:sid
            ORDER BY c.created_at ASC
        """), {"sid": sid}).fetchall()
        return jsonify({"ok": True, "items": [row_to_dict(r) for r in rows]})

    @app.route("/api/suggestions/<int:sid>/comments", methods=["POST"])
    @login_required_json
    def api_suggestions_comments_create(sid):
        uid = session["user_id"]
        data = request.get_json() or {}
        body = (data.get("body") or "").strip()
        if not body:
            return jsonify({"ok": False, "error": "body_required"}), 400

        db.session.execute(text("""
            INSERT INTO suggestion_comments(suggestion_id, user_id, body)
            VALUES(:sid, :uid, :body)
        """), {"sid": sid, "uid": uid, "body": body})
        db.session.execute(text("""
            UPDATE suggestions SET comments_count = comments_count + 1 WHERE id=:sid
        """), {"sid": sid})
        db.session.commit()
        return jsonify({"ok": True})

    # ======================================================================

    # --- ДОДАНО: роут для віддачі медіафайлів ---
    @app.route("/media/<path:filename>")
    def media(filename):
        # читаємо з MEDIA_ROOT; у БД зберігається лише відносний шлях типу "user/3/covers/file.jpg"
        root = app.config["MEDIA_ROOT"]
        full = os.path.join(root, filename)
        if not os.path.isfile(full):
            return abort(404)
        return send_from_directory(root, filename)
    # ---------------------------------------------

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

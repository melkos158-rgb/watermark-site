import os
from flask import Flask, render_template, jsonify, request, session  # +jsonify, request, session

from db import init_app_db, close_db, db, User  # підключаємо БД тут

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

    # 1) підключаємо БД до Flask
    init_app_db(app)
    app.teardown_appcontext(close_db)

    # 2) тільки після ініціалізації БД — імпорт і реєстрація blueprints
    import auth           # auth.bp
    import profile        # profile.bp
    import chat           # chat.bp
    app.register_blueprint(auth.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(chat.bp)

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
        """
        Якщо маєш у моделі User поле pxp_month — воно використовується в першу чергу.
        Інакше падаємо назад на загальний pxp.
        """
        # пробуємо pxp_month
        if hasattr(User, "pxp_month"):
            u = User.query.order_by(User.pxp_month.desc(), User.id.asc()).first()
            if u:
                return u
        # fallback на pxp
        if hasattr(User, "pxp"):
            return User.query.order_by(User.pxp.desc(), User.id.asc()).first()
        return None

    def get_active_banner():
        """Повертає словник {image_path, link_url}. Якщо немає активного банера ТОП-1 — повертає дефолтний."""
        top1 = get_top1_user_this_month()
        if top1:
            rec = BannerAd.query.filter_by(active=True, user_id=top1.id).order_by(BannerAd.id.desc()).first()
            if rec:
                return {"image_path": rec.image_path, "link_url": rec.link_url or ""}
        # дефолт
        return {"image_path": DEFAULT_BANNER_IMG, "link_url": DEFAULT_BANNER_URL}

    # 3) доступні у всіх шаблонах
    @app.context_processor
    def inject_user():
        from flask import session
        u = User.query.get(session["user_id"]) if session.get("user_id") else None
        return dict(current_user=u, pxp=(u.pxp if u else 0))

    # === NEW: окремий контекст — банер завжди доступний у шаблонах (напр. index.html)
    @app.context_processor
    def inject_banner():
        return dict(banner=get_active_banner())

    # ===== ПУБЛІЧНІ СТОРІНКИ =====
    @app.route("/")
    def index():
        return render_template("index.html")  # banner доступний через context_processor

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

    @app.route("/photo")
    def photo():
        return render_template("photo.html")

    # === NEW: клік по банеру — якщо не залогінений, в логін; якщо залогінений — ведемо на link_url або на /
    @app.route("/ad/click")
    def ad_click():
        from flask import session, redirect, url_for, request
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        b = get_active_banner()
        if b.get("link_url"):
            return redirect(b["link_url"])
        return redirect(url_for("index"))

    # === NEW: завантаження банера для ТОП-1
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

    @app.route("/admin")
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

    # === NEW: admin PXP add ===
    @app.route("/admin/pxp-add", methods=["POST"])
    @admin_required
    def admin_pxp_add():
        from flask import request, redirect, url_for, flash

        def to_int(v):
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
            user.pxp = to_int(user.pxp) + amount

        if add_month and hasattr(User, "pxp_month"):
            user.pxp_month = to_int(user.pxp_month) + amount

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

    # Список ідей (топ за лайками, потім новіші)
    @app.route("/api/suggestions")
    def api_suggestions_list():
        rows = db.session.execute(text("""
            SELECT s.*, u.name AS author_name, u.email AS author_email
            FROM suggestions s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.likes DESC, s.created_at DESC
            LIMIT 100
        """)).fetchall()
        return jsonify({"ok": True, "items": [row_to_dict(r) for r in rows]})

    # Створити ідею (списує 1 PXP)
    @app.route("/api/suggestions", methods=["POST"])
    @login_required_json
    def api_suggestions_create():
        uid = session["user_id"]
        data = request.get_json() or {}
        title = (data.get("title") or "").strip()
        body  = (data.get("body") or "").strip()
        if not title:
            return jsonify({"ok": False, "error": "title_required"}), 400

        user = User.query.get(uid)
        if not user:
            return jsonify({"ok": False, "error": "no_user"}), 400
        if (getattr(user, "pxp", 0) or 0) < 1:
            return jsonify({"ok": False, "error": "not_enough_pxp"}), 402

        # списуємо 1 PXP і створюємо запис
        user.pxp = (user.pxp or 0) - 1

        # --- ДОДАНО: крос-БД отримання sid (Postgres/SQLite) ---
        engine = db.session.get_bind().dialect.name  # 'postgresql' або 'sqlite' тощо
        if engine == "postgresql":
            # у Postgres беремо id одразу
            sid = db.session.execute(
                text("INSERT INTO suggestions(user_id, title, body) VALUES(:uid, :title, :body) RETURNING id"),
                {"uid": uid, "title": title, "body": body}
            ).scalar()
        else:
            # SQLite (як було)
            db.session.execute(
                text("INSERT INTO suggestions(user_id, title, body) VALUES(:uid, :title, :body)"),
                {"uid": uid, "title": title, "body": body}
            )
            sid = db.session.execute(text("SELECT last_insert_rowid() AS id")).scalar()
        # --------------------------------------------------------

        db.session.execute(text("""
            INSERT INTO pxp_transactions(user_id, delta, reason) VALUES(:uid, -1, 'suggestion_post')
        """), {"uid": uid})
        db.session.commit()

        row = db.session.execute(text("""
            SELECT s.*, u.name AS author_name, u.email AS author_email
            FROM suggestions s JOIN users u ON u.id=s.user_id
            WHERE s.id=:sid
        """), {"sid": sid}).fetchone()
        return jsonify({"ok": True, "item": row_to_dict(row)})

    # Лайк (1 раз на користувача)
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

    # Коментарі — список
    @app.route("/api/suggestions/<int:sid>/comments")
    def api_suggestions_comments_list(sid):
        rows = db.session.execute(text("""
            SELECT c.*, u.name AS author_name, u.email AS author_email
            FROM suggestion_comments c
            JOIN users u ON u.id=c.user_id
            WHERE c.suggestion_id=:sid
            ORDER BY c.created_at ASC
        """), {"sid": sid}).fetchall()
        return jsonify({"ok": True, "items": [row_to_dict(r) for r in rows]})

    # Додати коментар
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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

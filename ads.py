
from flask import session, request, redirect

# ads.py
# Банер TOP-1, завантаження банера та кілька адмін-ендпоінтів.

import os
from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_from_directory,
    current_app,
)
from sqlalchemy import text

from db import db, User

bp = Blueprint("ads", __name__)

# === конфіг ===

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
DEFAULT_BANNER_IMG = os.getenv("DEFAULT_BANNER_IMG", "ads/default_banner.jpg")
DEFAULT_BANNER_URL = os.getenv("DEFAULT_BANNER_URL", "")


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


# === модель банера ===

class BannerAd(db.Model):
    __tablename__ = "banner_ad"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    link_url = db.Column(db.String(500))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# === хелпер для адміна тільки тут (без циклічного імпорту) ===

def admin_required(f):
    from functools import wraps

    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Доступ лише для адміністратора.")
            return redirect(url_for("core.index"))
        return f(*args, **kwargs)

    return _wrap


# === TOP-1 + активний банер ===

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
        rec = (
            BannerAd.query.filter_by(active=True, user_id=top1.id)
            .order_by(BannerAd.id.desc())
            .first()
        )
        if rec:
            return {"image_path": rec.image_path, "link_url": rec.link_url or ""}
    return {"image_path": DEFAULT_BANNER_IMG, "link_url": DEFAULT_BANNER_URL}


@bp.context_processor
def inject_banner():
    return dict(banner=get_active_banner())


# === /ad + адмін-банер ===

@bp.route("/ad/click")
def ad_click():
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=request.path))
    b = get_active_banner()
    if b.get("link_url"):
        return redirect(b["link_url"])
    return redirect(url_for("core.index"))


@bp.route("/ad/upload", methods=["GET", "POST"])
def ad_upload():

    # ✅ session-based auth compatibility (works with your current site auth)
    uid = session.get("user_id")
    if not uid:
        nxt = (request.full_path or request.path or "/").rstrip("?")
        return redirect(f"/login?next={nxt}")

    user = User.query.get(uid)
    if not user:
        nxt = (request.full_path or request.path or "/").rstrip("?")
        return redirect(f"/login?next={nxt}")

    top1 = get_top1_user_this_month()
    if not top1 or top1.id != user.id:
        flash("Завантажувати банер може лише користувач із TOP-1 цього місяця.")
        return redirect(url_for("core.index"))

    if request.method == "POST":
        f = request.files.get("image")
        link_url = request.form.get("link_url") or ""
        if not f or not allowed_file(f.filename):
            flash("Завантаж зображення .png/.jpg/.jpeg/.webp")
            return redirect(url_for("ads.ad_upload"))

        from werkzeug.utils import secure_filename

        fname = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"
        save_rel = os.path.join("ads", fname).replace("\\", "/")
        save_abs = os.path.join("static", save_rel)
        os.makedirs(os.path.dirname(save_abs), exist_ok=True)
        f.save(save_abs)

        BannerAd.query.filter_by(user_id=user.id, active=True).update({"active": False})
        db.session.add(
            BannerAd(
                user_id=user.id,
                image_path=save_rel,
                link_url=link_url,
                active=True,
            )
        )
        db.session.commit()
        flash("Банер оновлено! Він уже на головній.")
        return redirect(url_for("core.index"))

    return render_template("ad_upload_inline.html")


@bp.route("/admin/disable-top-banner", methods=["POST"])
@admin_required
def admin_disable_top_banner():
    top1 = get_top1_user_this_month()
    if top1:
        BannerAd.query.filter_by(user_id=top1.id, active=True).update(
            {"active": False}
        )
        db.session.commit()
    flash("Банер TOP-1 вимкнено. Показується дефолтний.")
    return redirect(url_for("admin_panel"))


@bp.route("/admin/banner-default", methods=["POST"])
@admin_required
def admin_banner_default():
    f = request.files.get("image")
    link_url = request.form.get("link_url") or ""
    if not f or not allowed_file(f.filename):
        flash("Дай .png/.jpg/.jpeg/.webp")
        return redirect(url_for("admin_panel"))

    from werkzeug.utils import secure_filename

    ext = f.filename.rsplit(".", 1)[1].lower()
    fname = f"default_banner.{ext}"
    save_rel = os.path.join("ads", fname).replace("\\", "/")
    save_abs = os.path.join("static", save_rel)
    os.makedirs(os.path.dirname(save_abs), exist_ok=True)
    f.save(save_abs)

    # оновлюємо глобальні змінні в конфігу Flask
    current_app.config["DEFAULT_BANNER_IMG"] = save_rel
    current_app.config["DEFAULT_BANNER_URL"] = link_url

    global DEFAULT_BANNER_IMG, DEFAULT_BANNER_URL
    DEFAULT_BANNER_IMG = save_rel
    DEFAULT_BANNER_URL = link_url

    flash("Дефолтний банер оновлено.")
    return redirect(url_for("admin_panel"))

# auth.py
import os
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from authlib.integrations.flask_client import OAuth
from db import db, User

bp = Blueprint("auth", __name__, url_prefix="")

# ---- Google OAuth (вмикається лише якщо всі змінні присутні) ----
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI   = os.environ.get("OAUTH_REDIRECT_URI")  # напр.: https://<your-app>.up.railway.app/auth/callback

oauth = OAuth()
google = None
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and OAUTH_REDIRECT_URI:
    google = oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        access_token_url="https://oauth2.googleapis.com/token",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        userinfo_endpoint="https://www.googleapis.com/oauth2/v2/userinfo",
        client_kwargs={"scope": "openid email profile"},
        authorize_params={"prompt": "select_account"},
    )

@bp.record_once
def _setup_oauth(setup_state):
    app = setup_state.app
    oauth.init_app(app)

# ---- helpers ----
def _safe_next(next_url: str | None, fallback_endpoint: str = "profile.profile"):
    """
    Дозволяємо редірект тільки на внутрішні шляхи типу '/profile'.
    Забороняємо схеми http(s):// і дві косі '//' (open redirect).
    """
    if not next_url:
        return url_for(fallback_endpoint)
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return url_for(fallback_endpoint)

# ---------------------------
# Email-реєстрація/вхід (fallback)
# ---------------------------
@bp.get("/register")
def register():
    # шаблон може прочитати ?next= сам (у тебе вже є JS), але на всяк передамо теж
    return render_template("register.html", next=request.args.get("next"))

@bp.post("/register")
def register_post():
    email = (request.form.get("email") or "").strip().lower()
    name  = (request.form.get("name") or "").strip()
    next_url = request.args.get("next") or request.form.get("next")

    if not email:
        flash("Введи email", "error")
        return redirect(url_for("auth.register", next=next_url))

    u = User.query.filter_by(email=email).first()
    if u:
        session["user_id"] = u.id
        flash("Вже зареєстрований — увійшли.", "success")
        return redirect(_safe_next(next_url))

    u = User(email=email, name=name)
    db.session.add(u)
    db.session.commit()

    session["user_id"] = u.id
    flash("Реєстрація успішна.", "success")
    return redirect(_safe_next(next_url))

@bp.get("/login")
def login():
    # покажемо кнопку Google тільки якщо налаштовано
    return render_template("login.html", google_enabled=bool(google), next=request.args.get("next"))

@bp.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    next_url = request.args.get("next") or request.form.get("next")

    u = User.query.filter_by(email=email).first()
    if not u:
        flash("Користувача не знайдено. Зареєструйся.", "error")
        return redirect(url_for("auth.register", next=next_url))

    session["user_id"] = u.id
    flash("Увійшли.", "success")
    return redirect(_safe_next(next_url))

@bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("Вийшли.", "success")
    return redirect(url_for("index"))

# ---------------------------
# Google OAuth
# ---------------------------
@bp.get("/auth/google")
def google_login():
    if not google:
        flash("Google OAuth не налаштований.", "error")
        return redirect(url_for("auth.login"))

    # збережемо куди повертатись
    next_url = request.args.get("next")
    if next_url:
        session["next_after_oauth"] = next_url

    # перенаправляємо на Google
    return google.authorize_redirect(redirect_uri=OAUTH_REDIRECT_URI)

@bp.get("/auth/callback")
def google_callback():
    if not google:
        flash("Google OAuth не налаштований.", "error")
        return redirect(url_for("auth.login"))

    try:
        token = google.authorize_access_token()
        info  = google.get("userinfo").json()
        email = (info.get("email") or "").lower()
        name  = info.get("name") or ""
        avatar = info.get("picture") or ""
        gid = info.get("id") or info.get("sub") or ""

        if not email:
            flash("Google не повернув email.", "error")
            return redirect(url_for("auth.login"))

        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, name=name, google_id=gid, avatar=avatar)
            db.session.add(u)
        else:
            # оновимо google_id / avatar якщо з’явились
            if gid and not getattr(u, "google_id", None):
                u.google_id = gid
            if avatar and not getattr(u, "avatar", None):
                u.avatar = avatar

        db.session.commit()
        session["user_id"] = u.id
        flash("Успішний вхід через Google.", "success")

        next_url = session.pop("next_after_oauth", None)
        return redirect(_safe_next(next_url))
    except Exception:
        flash("Помилка авторизації через Google ❌", "error")
        return redirect(url_for("auth.login"))
# auth.py
import os
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from authlib.integrations.flask_client import OAuth
from db import db, User

bp = Blueprint("auth", __name__, url_prefix="")

# ---- Google OAuth (вмикається лише якщо всі змінні присутні) ----
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI   = os.environ.get("OAUTH_REDIRECT_URI")  # напр.: https://<your-app>.up.railway.app/auth/callback

oauth = OAuth()
google = None
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and OAUTH_REDIRECT_URI:
    google = oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        access_token_url="https://oauth2.googleapis.com/token",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        userinfo_endpoint="https://www.googleapis.com/oauth2/v2/userinfo",
        client_kwargs={"scope": "openid email profile"},
        authorize_params={"prompt": "select_account"},
    )

@bp.record_once
def _setup_oauth(setup_state):
    app = setup_state.app
    oauth.init_app(app)

# ---- helpers ----
def _safe_next(next_url: str | None, fallback_endpoint: str = "profile.profile"):
    """
    Дозволяємо редірект тільки на внутрішні шляхи типу '/profile'.
    Забороняємо схеми http(s):// і дві косі '//' (open redirect).
    """
    if not next_url:
        return url_for(fallback_endpoint)
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return url_for(fallback_endpoint)

# ---------------------------
# Email-реєстрація/вхід (fallback)
# ---------------------------
@bp.get("/register")
def register():
    # шаблон може прочитати ?next= сам (у тебе вже є JS), але на всяк передамо теж
    return render_template("register.html", next=request.args.get("next"))

@bp.post("/register")
def register_post():
    email = (request.form.get("email") or "").strip().lower()
    name  = (request.form.get("name") or "").strip()
    next_url = request.args.get("next") or request.form.get("next")

    if not email:
        flash("Введи email", "error")
        return redirect(url_for("auth.register", next=next_url))

    u = User.query.filter_by(email=email).first()
    if u:
        session["user_id"] = u.id
        flash("Вже зареєстрований — увійшли.", "success")
        return redirect(_safe_next(next_url))

    u = User(email=email, name=name)
    db.session.add(u)
    db.session.commit()

    session["user_id"] = u.id
    flash("Реєстрація успішна.", "success")
    return redirect(_safe_next(next_url))

@bp.get("/login")
def login():
    # покажемо кнопку Google тільки якщо налаштовано
    return render_template("login.html", google_enabled=bool(google), next=request.args.get("next"))

@bp.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    next_url = request.args.get("next") or request.form.get("next")

    u = User.query.filter_by(email=email).first()
    if not u:
        flash("Користувача не знайдено. Зареєструйся.", "error")
        return redirect(url_for("auth.register", next=next_url))

    session["user_id"] = u.id
    flash("Увійшли.", "success")
    return redirect(_safe_next(next_url))

@bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("Вийшли.", "success")
    return redirect(url_for("index"))

# ---------------------------
# Google OAuth
# ---------------------------
@bp.get("/auth/google")
def google_login():
    if not google:
        flash("Google OAuth не налаштований.", "error")
        return redirect(url_for("auth.login"))

    # збережемо куди повертатись
    next_url = request.args.get("next")
    if next_url:
        session["next_after_oauth"] = next_url

    # перенаправляємо на Google
    return google.authorize_redirect(redirect_uri=OAUTH_REDIRECT_URI)

@bp.get("/auth/callback")
def google_callback():
    if not google:
        flash("Google OAuth не налаштований.", "error")
        return redirect(url_for("auth.login"))

    try:
        token = google.authorize_access_token()
        info  = google.get("userinfo").json()
        email = (info.get("email") or "").lower()
        name  = info.get("name") or ""
        avatar = info.get("picture") or ""
        gid = info.get("id") or info.get("sub") or ""

        if not email:
            flash("Google не повернув email.", "error")
            return redirect(url_for("auth.login"))

        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, name=name, google_id=gid, avatar=avatar)
            db.session.add(u)
        else:
            # оновимо google_id / avatar якщо з’явились
            if gid and not getattr(u, "google_id", None):
                u.google_id = gid
            if avatar and not getattr(u, "avatar", None):
                u.avatar = avatar

        db.session.commit()
        session["user_id"] = u.id
        flash("Успішний вхід через Google.", "success")

        next_url = session.pop("next_after_oauth", None)
        return redirect(_safe_next(next_url))
    except Exception:
        flash("Помилка авторизації через Google ❌", "error")
        return redirect(url_for("auth.login"))

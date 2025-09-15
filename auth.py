# auth.py
import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from authlib.integrations.flask_client import OAuth
from db import db, User

bp = Blueprint("auth", __name__, url_prefix="")

# Google OAuth вмикаємо тільки якщо всі змінні задані
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URI   = os.environ.get("OAUTH_REDIRECT_URI")  # https://<railway>.app/auth/callback

oauth = OAuth()
google = None
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and OAUTH_REDIRECT_URI:
    google = oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        access_token_url="https://oauth2.googleapis.com/token",
        access_token_params=None,
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        authorize_params={"prompt": "select_account"},
        api_base_url="https://www.googleapis.com/oauth2/v2/",
        userinfo_endpoint="https://www.googleapis.com/oauth2/v2/userinfo",
        client_kwargs={"scope": "openid email profile"},
    )

@bp.record_once
def setup_oauth(setup_state):
    app = setup_state.app
    oauth.init_app(app)

# --- простий email-логін/реєстрація (fallback) ---
@bp.get("/register")
def register():
    return render_template("register.html")

@bp.post("/register")
def register_post():
    email = (request.form.get("email") or "").strip().lower()
    name  = (request.form.get("name") or "").strip()
    if not email:
        flash("Введи email", "error"); return redirect(url_for("auth.register"))
    u = User.query.filter_by(email=email).first()
    if u:
        session["user_id"] = u.id
        flash("Вже зареєстрований — увійшли.", "success")
        return redirect(url_for("profile.profile"))
    u = User(email=email, name=name)
    db.session.add(u); db.session.commit()
    session["user_id"] = u.id
    flash("Реєстрація успішна.", "success")
    return redirect(url_for("profile.profile"))

@bp.get("/login")
def login():
    return render_template("login.html", google_enabled=bool(google))

@bp.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    u = User.query.filter_by(email=email).first()
    if not u:
        flash("Користувача не знайдено. Зареєструйся.", "error")
        return redirect(url_for("auth.register"))
    session["user_id"] = u.id
    flash("Увійшли.", "success")
    return redirect(url_for("profile.profile"))

@bp.get("/auth/google")
def google_login():
    if not google:
        flash("Google OAuth не налаштований.", "error")
        return redirect(url_for("auth.login"))
    return google.authorize_redirect(redirect_uri=OAUTH_REDIRECT_URI)

@bp.get("/auth/callback")
def google_callback():
    if not google:
        flash("Google OAuth не налаштований.", "error")
        return redirect(url_for("auth.login"))
    token = google.authorize_access_token()  # якщо redirect_uri не співпаде — тут була твоя 400/401
    info  = google.get("userinfo").json()
    email = (info.get("email") or "").lower()
    name  = info.get("name")
    if not email:
        flash("Не вдалося отримати email від Google.", "error")
        return redirect(url_for("auth.login"))
    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(email=email, name=name)
        db.session.add(u); db.session.commit()
    session["user_id"] = u.id
    flash("Успішний вхід через Google.", "success")
    return redirect(url_for("profile.profile"))

@bp.post("/logout")
def logout():
    session.clear()
    flash("Вийшли.", "success")
    return redirect(url_for("index"))

        flash("Помилка авторизації через Google ❌")
        return redirect(url_for("auth.login"))

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
import os, secrets, string
from authlib.integrations.flask_client import OAuth
from db import get_db, ensure_login_code_column, PSQL_URL

bp = Blueprint("auth", __name__)

oauth = OAuth()
google = None

@bp.record_once
def _setup_oauth(setup_state):
    app = setup_state.app
    oauth.init_app(app)
    global google
    google = oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "prompt": "select_account"},
    )

# ===== current_user =====
class Guest:
    is_authenticated = False
    id = None
    email = None
    name = None
    avatar = None
    pxp = 0

def _make_user(email, name=None, uid=None):
    U = type("User", (), {})
    u = U()
    u.is_authenticated = True
    u.email = email
    u.name = name
    u.id = uid
    return u

def _load_current_user():
    email = session.get("email")
    uid   = session.get("user_id")
    name  = session.get("name")
    if not email and not uid:
        return Guest()
    try:
        db = get_db()
        row = db.execute(
            "SELECT id, email, name, avatar, COALESCE(pxp,0) AS pxp FROM users "
            "WHERE " + ("id=?" if uid else "email=?"),
            (uid if uid else email,)
        ).fetchone()
        if row:
            d = dict(row) if hasattr(row, "keys") else dict(row)
            u = _make_user(d.get("email"), d.get("name"), d.get("id"))
            u.avatar = d.get("avatar"); u.pxp = d.get("pxp") or 0
            return u
    except Exception:
        pass
    u = _make_user(email or "user@local", name, uid)
    u.avatar = session.get("avatar"); u.pxp = session.get("pxp", 0)
    return u

@bp.before_app_request
def attach_user():
    g.user = _load_current_user()

@bp.app_context_processor
def inject_user():
    return dict(current_user=g.get("user", Guest()))

# ===== helpers =====
def _db_create_user(email, name, password):
    try:
        db = get_db()
        db.execute("INSERT INTO users (email, name, password, pxp, name_changes) VALUES (?, ?, ?, 0, 0)",
                   (email, name, password))
        db.commit()
        row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row: return (dict(row) if hasattr(row, "keys") else dict(row)).get("id")
    except Exception:
        try:
            db = get_db()
            row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if row: return (dict(row) if hasattr(row, "keys") else dict(row)).get("id")
        except Exception:
            pass
    return None

def _db_check_password(email, password):
    try:
        db = get_db()
        row = db.execute("SELECT id, email, name, password FROM users WHERE email=?", (email,)).fetchone()
        if row:
            d = dict(row) if hasattr(row, "keys") else dict(row)
            if d.get("password") == password:
                return d
    except Exception:
        pass
    return None

def _save_code_for_user(uid, code):
    try:
        db = get_db()
        db.execute("UPDATE users SET login_code=? WHERE id=?", (code, uid))
        db.commit()
    except Exception:
        pass

def _gen_code(n=16):
    import string, secrets
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))

# ===== routes =====
@bp.route("/login")
def login():
    return render_template("login.html")

@bp.route("/login_local", methods=["POST"])
def login_local():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    row = _db_check_password(email, password)
    if row:
        session["user_id"] = row.get("id")
        session["email"]   = row.get("email")
        session["name"]    = row.get("name")
        flash("Успішний вхід ✅")
        return redirect(request.args.get("next") or url_for("index"))

    # тестовий fallback
    if email == "test@test.com" and password == "123":
        session["email"] = email; session["name"] = "Test User"
        flash("Успішний вхід ✅"); return redirect(url_for("index"))

    flash("Невірні дані ❌")
    return redirect(url_for("auth.login"))

@bp.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip() or None
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not email or not password:
            flash("Вкажи email і пароль ❌"); return redirect(url_for("auth.register"))
        uid = _db_create_user(email, name, password)
        ensure_login_code_column()
        code = _gen_code(16)
        if uid: _save_code_for_user(uid, code)
        session["user_id"]=uid; session["email"]=email; session["name"]=name; session["login_code"]=code
        flash(f"Реєстрація успішна ✅ Твій код: {code}")
        return redirect(request.args.get("next") or url_for("profile.profile"))
    return render_template("register.html")

@bp.route("/logout")
def logout():
    session.clear()
    flash("Ви вийшли з акаунта", "info")
    return redirect(url_for("index"))

@bp.route("/login_google")
def login_google():
    redirect_uri = url_for("auth.auth_google_callback", _external=True, _scheme="https")
    return google.authorize_redirect(redirect_uri)

@bp.route("/login/google/callback")
def auth_google_callback():
    try:
        token = google.authorize_access_token()
        resp  = google.get("userinfo")
        info  = resp.json() if resp else {}
        email = (info.get("email") or "").lower()
        if not email:
            flash("Не вдалося отримати email з Google ❌")
            return redirect(url_for("auth.login"))
        try:
            db = get_db()
            db.execute(
                "INSERT OR IGNORE INTO users (email, name, avatar, bio, pxp, name_changes, password) "
                "VALUES (?, ?, ?, ?, 0, 0, '')",
                (email, info.get("name"), info.get("picture"), "")
            )
            db.commit()
        except Exception:
            pass
        session["email"]=email; session["name"]=info.get("name")
        flash(f"Вхід через Google: {email} ✅")
        return redirect(url_for("index"))
    except Exception:
        flash("Помилка авторизації через Google ❌")
        return redirect(url_for("auth.login"))

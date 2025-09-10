import os
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    current_user, login_required
)
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth

# ================== ENV / APP ==================
load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret-change-me")

# ================== LOGIN MANAGER ==================
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, id, name=None, email=None, avatar=None, pw_hash=None):
        self.id = id
        self.name = name or id
        self.email = email or id
        self.avatar = avatar
        self.pw_hash = pw_hash

# In-memory “БД”. Для продакшену заміниш на реальну БД.
USERS: dict[str, User] = {}

@login_manager.user_loader
def load_user(user_id):
    return USERS.get(user_id)

# ================== OAUTH (GOOGLE) ==================
oauth = OAuth(app)
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ================== GLOBALS FOR JINJA ==================
@app.context_processor
def inject_globals():
    return {"pxp": session.get("pxp", 0), "current_user": current_user}

# ================== SITE PAGES (під твої файли) ==================
@app.route("/")
def index():               return render_template("index.html", page="index")

@app.route("/stl")
def stl():                 return render_template("stl.html", page="stl")

@app.route("/video")
def video():               return render_template("video.html", page="video")

@app.route("/edit_photo")
def edit_photo():          return render_template("edit_photo.html", page="edit_photo")

@app.route("/enhance")
def enhance():             return render_template("enhance.html", page="enhance")

@app.route("/photo")
def photo():               return render_template("photo.html", page="photo")

@app.route("/donate")
def donate():              return render_template("donate.html", page="donate")

@app.route("/top100")
def top100():              return render_template("top100.html", page="top100")

@app.route("/profile")
@login_required
def profile():             return render_template("profile.html", page="profile")

# Залишаємо для кнопки “До профілю” на donate.html
@app.route("/pxp")
@login_required
def pxp_page():            return render_template("PXP.html", page="pxp")

# ================== AUTH ==================
@app.route("/login", methods=["GET"])
def login():               return render_template("login.html", page="login")

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        name = (request.form.get("name") or "").strip() or email

        if not email or not password:
            flash("Вкажи email і пароль")
            return redirect(url_for("register"))

        # Заборона дублю локального акаунта
        if email in USERS and USERS[email].pw_hash:
            flash("Користувач вже існує")
            return redirect(url_for("register"))

        pw_hash = generate_password_hash(password)
        user = USERS.get(email) or User(id=email, name=name, email=email)
        user.pw_hash = pw_hash
        USERS[email] = user

        login_user(user)
        session.setdefault("pxp", 0)
        return redirect(url_for("profile"))
    return render_template("register.html", page="register")

@app.route("/login/local", methods=["POST"])
def login_local():
    email = (request.form.get("email") or "").strip().lower()
    password = (request.form.get("password") or "").strip()
    user = USERS.get(email)

    if not user or not user.pw_hash or not check_password_hash(user.pw_hash, password):
        flash("Невірний email або пароль")
        return redirect(url_for("login"))

    login_user(user)
    session.setdefault("pxp", 0)
    return redirect(url_for("profile"))

# ================== GOOGLE OAUTH FLOW ==================
@app.route("/login/google")
def login_google():
    redirect_uri = url_for("auth_google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route("/auth/google/callback")
def auth_google_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or oauth.google.parse_id_token(token)

    email = (userinfo.get("email") or "").lower()
    if not email:
        flash("Google не повернув email")
        return redirect(url_for("login"))

    name = userinfo.get("name", email)
    picture = userinfo.get("picture")

    user = USERS.get(email) or User(id=email, name=name, email=email, avatar=picture)
    USERS[email] = user
    login_user(user)

    session.setdefault("pxp", 0)
    return redirect(url_for("profile"))

# ================== ENTRY ==================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)



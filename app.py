from flask import Flask, render_template, request, redirect, url_for, flash, session, g
import os
import sqlite3

# --- NEW: Authlib для Google OAuth ---
from authlib.integrations.flask_client import OAuth

# -----------------------------
# APP INIT
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "devsecret")  # для flash()

# --- SQLite (працює, якщо задано DB_PATH і створена таблиця users) ---
DB_PATH = os.environ.get("DB_PATH", "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---- дефолти для шаблонів ----
class Guest:
    is_authenticated = False
    name = None
    email = None

@app.context_processor
def inject_defaults():
    # це був твій дефолт — залишаю як є
    return dict(current_user=Guest(), pxp=0)

def safe_render(tpl, fallback_text):
    try:
        return render_template(tpl)
    except Exception:
        # щоб бачити точну причину — дивись View logs у Railway
        return fallback_text

# --- NEW: реєструємо Google OAuth провайдера через OpenID Discovery ---
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    # Authlib підтягне коректні endpoint-и з discovery-документу
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile", "prompt": "select_account"},
)

# ======================================================
# ✅ ДОДАНО: простий user-loader + контекст, що ПЕРЕКРИВАЄ Guest
# ======================================================
def _make_user(email, name=None, uid=None):
    U = type("User", (), {})  # легкий об’єкт
    u = U()
    u.is_authenticated = True
    u.email = email
    u.name = name
    u.id = uid
    return u

def load_current_user():
    """Читаємо з session і, якщо можливо, доповнюємо з БД."""
    email = session.get("email")
    uid = session.get("user_id")
    name = session.get("name")
    if not email and not uid:
        return Guest()
    # спробуємо підтягнути ім’я з БД (якщо є)
    try:
        db = get_db()
        if uid:
            row = db.execute("SELECT id, email, name FROM users WHERE id=?", (uid,)).fetchone()
        elif email:
            row = db.execute("SELECT id, email, name FROM users WHERE email=?", (email,)).fetchone()
        else:
            row = None
        if row:
            return _make_user(row["email"], row["name"], row["id"])
    except Exception:
        pass
    # якщо БД нема — повертаємо сесійну інформацію
    return _make_user(email or "user@local", name, uid)

# цей контекст-процесор реєструється ПІСЛЯ твого й тим самим перекриває current_user
@app.context_processor
def inject_auth_user():
    return dict(current_user=load_current_user())

# ======================================================
# ✅ ДОДАНО: захист для певних сторінок + автологін при /register і /login_local
#   (без зміни твоїх існуючих функцій — перехоплюємо на рівні before_request)
# ======================================================
PROTECTED_ENDPOINTS = {"top100", "donate", "profile"}  # тільки для залогінених

def _db_create_user(email, name, password):
    """Спроба створити користувача в БД. Повертає (uid|None)."""
    try:
        db = get_db()
        db.execute(
            "INSERT INTO users (email, name, password, pxp, name_changes) VALUES (?, ?, ?, 0, 0)",
            (email, name, password)
        )
        db.commit()
        row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        return row["id"] if row else None
    except sqlite3.IntegrityError:
        # користувач існує — дістанемо id
        try:
            db = get_db()
            row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            return row["id"] if row else None
        except Exception:
            return None
    except Exception:
        return None

def _db_check_password(email, password):
    """Проста перевірка пароля в БД (тимчасово — у відкритому вигляді, як у тебе)."""
    try:
        db = get_db()
        row = db.execute("SELECT id, email, name, password FROM users WHERE email=?", (email,)).fetchone()
        if row and row["password"] == password:
            return row
    except Exception:
        pass
    return None

@app.before_request
def auth_gate_and_shortcuts():
    # --- LOGOUT: перехоплюємо та очищаємо сесію і кидаємо на головну
    if request.endpoint == "logout":
        session.clear()
        return redirect(url_for("index"))  # ← редірект після виходу

    # --- PROTECT PAGES: top100 / donate / profile вимагають логіну
    if request.endpoint in PROTECTED_ENDPOINTS:
        if not getattr(load_current_user(), "is_authenticated", False):
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=next_url))

    # --- LOGIN_LOCAL: зробимо реальний логін до виклику твого хендлера
    if request.endpoint == "login_local" and request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        row = _db_check_password(email, password)
        if row:
            session["user_id"] = row["id"]
            session["email"] = row["email"]
            session["name"] = row["name"]
            flash("Успішний вхід ✅")
            # якщо є next — поважаємо
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        # fallback на тестові креденшли, як у тебе
        if email == "test@test.com" and password == "123":
            session["email"] = email
            session["name"] = "Test User"
            flash("Успішний вхід ✅")
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("Невірний email або пароль ❌")
        return redirect(url_for("login"))

    # --- REGISTER: автологін і редірект одразу без другого кола
    if request.endpoint == "register" and request.method == "POST":
        name = (request.form.get("name") or "").strip() or None
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not email or not password:
            flash("Вкажи email і пароль ❌")
            return redirect(url_for("register"))

        uid = _db_create_user(email, name, password)  # якщо БД нема — поверне None
        # Автологін навіть без БД: тримаємо у сесії
        session["user_id"] = uid
        session["email"] = email
        session["name"] = name
        flash("Реєстрація успішна ✅ Ви вже увійшли.")
        # Поважаємо next, якщо юзер намагався потрапити в закриту сторінку
        next_url = request.args.get("next") or url_for("profile")
        return redirect(next_url)

# ======================================================
# ТВОЇ МАРШРУТИ (НЕ ЧІПАВ, тільки нижче ми керуємо доступом через before_request)
# ======================================================
@app.route("/")
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

# ✅ ДОДАНО: сторінка Photo (твій photo.html)
@app.route("/photo")
def photo():
    return render_template("photo.html")

# сторінки, що зараз падають → рендеримо безпечно
@app.route("/top100")
def top100():
    return safe_render("top100.html", "Top100 page (тимчасова заглушка)")

@app.route("/donate")
def donate():
    return safe_render("donate.html", "Donate page (тимчасова заглушка)")

@app.route("/login")
def login():
    return safe_render("login.html", "Login page (тимчасова заглушка)")

# ---- ВИПРАВЛЕНО: дозволено POST і запис у БД, якщо є ----
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip() or None
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Вкажи email і пароль ❌")
            return redirect(url_for("register"))

        # намагаємось записати в SQLite (якщо DB_PATH/таблиця є)
        try:
            db = get_db()
            db.execute(
                "INSERT INTO users (email, name, password, pxp, name_changes) VALUES (?, ?, ?, 0, 0)",
                (email, name, password)
            )
            db.commit()
            flash("Користувача створено ✅ Тепер увійди.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Такий email вже зареєстрований ❌")
            return redirect(url_for("register"))
        except Exception:
            # якщо БД ще не налаштована — не падаємо, просто показуємо повідомлення
            flash("Реєстрація тимчасово без БД — налаштуй DB_PATH/таблицю users. ✅ Форма працює.")
            return redirect(url_for("login"))

    # GET:
    return safe_render("register.html", "Register page (тимчасова заглушка)")

@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/logout")
def logout():
    return "Logout OK"

# ---- ДОДАНО раніше: обробники для логіну ----
@app.route("/login_local", methods=["POST"])
def login_local():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    # тимчасова перевірка (пізніше підключимо справжній логін із БД)
    try:
        db = get_db()
        row = db.execute(
            "SELECT id, email, name, password FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        if row and row["password"] == password:
            flash("Успішний вхід ✅")
            return redirect(url_for("index"))
    except Exception:
        # якщо БД ще не готова — fallback на тестові креденшли
        if email == "test@test.com" and password == "123":
            flash("Успішний вхід ✅")
            return redirect(url_for("index"))

    flash("Невірний email або пароль ❌")
    return redirect(url_for("login"))

# ---- UPDATED: прибрав блокуючу перевірку env, щоб Google стартував ----
@app.route("/login_google")
def login_google():
    # навіть якщо змінні не підхопились, нехай спробує; помилку побачимо в логах
    redirect_uri = url_for("auth_google_callback", _external=True, _scheme="https")
    return google.authorize_redirect(redirect_uri)

# ---- NEW: callback від Google ----
@app.route("/login/google/callback")
def auth_google_callback():
    try:
        token = google.authorize_access_token()
        resp = google.get("userinfo")
        info = resp.json() if resp else {}
        email = (info.get("email") or "").lower()
        if not email:
            flash("Не вдалося отримати email з Google ❌")
            return redirect(url_for("login"))

        # створимо користувача, якщо його ще немає
        try:
            db = get_db()
            db.execute(
                "INSERT OR IGNORE INTO users (email, name, avatar, bio, pxp, name_changes, password) "
                "VALUES (?, ?, ?, ?, 0, 0, '')",
                (email, info.get("name"), info.get("picture"), "")
            )
            db.commit()
        except Exception:
            # якщо БД не готова — все одно логінимось "мʼяко"
            pass

        # ✅ ДОДАНО: залогінити через сесію (перехопити ми не можемо після цього роута)
        session["email"] = email
        session["name"] = info.get("name")
        flash(f"Вхід через Google: {email} ✅")
        return redirect(url_for("index"))
    except Exception:
        flash("Помилка авторизації через Google ❌")
        return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)




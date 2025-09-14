from flask import Flask, render_template, request, redirect, url_for, flash, session, g
import os
import sqlite3
# ADDED: для довгих кодів
import secrets
import string
import chat

# ---- NEW: Postgres (опційно, якщо є DATABASE_URL)
PSQL_URL = os.getenv("DATABASE_URL")
if PSQL_URL:
    import psycopg2
    import psycopg2.extras

# --- NEW: Authlib для Google OAuth ---
from authlib.integrations.flask_client import OAuth

# -----------------------------
# APP INIT
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "devsecret")  # для flash()

# --- SQLite (фолбек, якщо НЕ задано DATABASE_URL) ---
DB_PATH = os.environ.get("DB_PATH", "database.db")

# ------- ADDED: маленький адаптер, щоб код з sqlite .execute() працював і з Postgres -------
class _PsqlAdapter:
    def __init__(self, conn):
        self._conn = conn
    def execute(self, sql, params=()):
        # заміна плейсхолдерів: з '?' (sqlite-стиль) на '%s' (psycopg2)
        q = []
        for ch in sql:
            q.append('%s' if ch == '?' else ch)
        sql_psql = ''.join(q)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql_psql, params)
        return cur
    def commit(self):
        self._conn.commit()

USERS_TABLE_OK = False  # щоб створювати таблицю лише раз

def _ensure_users_table(db, engine: str):
    """
    Створює таблицю users, якщо її немає.
    engine: 'psql' або 'sqlite'
    """
    global USERS_TABLE_OK
    if USERS_TABLE_OK:
        return
    try:
        if engine == 'psql':
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    avatar TEXT,
                    bio TEXT,
                    pxp INTEGER DEFAULT 0,
                    name_changes INTEGER DEFAULT 0,
                    password TEXT NOT NULL,
                    login_code TEXT
                )
            """)
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_code ON users(login_code)")
            db.commit()
        else:
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    avatar TEXT,
                    bio TEXT,
                    pxp INTEGER DEFAULT 0,
                    name_changes INTEGER DEFAULT 0,
                    password TEXT NOT NULL,
                    login_code TEXT
                )
            """)
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_code ON users(login_code)")
            db.commit()
        USERS_TABLE_OK = True
    except Exception:
        # тихо ідемо далі — якщо нема прав або це не потрібно
        pass

def get_db():
    """
    Повертає об’єкт з методом .execute(...).fetchone() і .commit(),
    як у sqlite, але працює і з Postgres (через адаптер).
    """
    if PSQL_URL:
        conn = psycopg2.connect(PSQL_URL)
        db = _PsqlAdapter(conn)
        _ensure_users_table(db, 'psql')
        return db
    # fallback: sqlite
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    db = conn
    _ensure_users_table(db, 'sqlite')
    return db

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
            r = row if isinstance(row, dict) else dict(row)
            return _make_user(r.get("email"), r.get("name"), r.get("id"))
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
        if row:
            r = row if isinstance(row, dict) else dict(row)
            return r.get("id")
        return None
    except Exception:
        # може бути дубль або інша помилка — спробуємо зчитати існуючого
        try:
            db = get_db()
            row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if row:
                r = row if isinstance(row, dict) else dict(row)
                return r.get("id")
        except Exception:
            return None
    return None

def _db_check_password(email, password):
    """Проста перевірка пароля в БД (тимчасово — у відкритому вигляді, як у тебе)."""
    try:
        db = get_db()
        row = db.execute("SELECT id, email, name, password FROM users WHERE email=?", (email,)).fetchone()
        if row:
            r = row if isinstance(row, dict) else dict(row)
            if r.get("password") == password:
                return r
    except Exception:
        pass
    return None

# ----------------------------
# ADDED: підтримка довгого login_code
# ----------------------------
def _has_column(table, col):
    try:
        db = get_db()
        if PSQL_URL:
            row = db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=? AND column_name=?",
                (table, col)
            ).fetchone()
            return bool(row)
        else:
            cols = db.execute(f"PRAGMA table_info({table})").fetchall()
            for c in cols:
                name = c["name"] if isinstance(c, sqlite3.Row) else c.get("name")
                if name == col:
                    return True
            return False
    except Exception:
        return False

def _ensure_login_code_column():
    """Додає колонку login_code (UNIQUE), якщо її ще немає."""
    try:
        if not _has_column("users", "login_code"):
            db = get_db()
            db.execute("ALTER TABLE users ADD COLUMN login_code TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_code ON users(login_code)")
            db.commit()
    except Exception:
        pass

def _gen_code(length=16):
    """Довгий алфавітно-цифровий код (UPPERCASE+digits)."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def _save_code_for_user(uid, code):
    try:
        db = get_db()
        db.execute("UPDATE users SET login_code=? WHERE id=?", (code, uid))
        db.commit()
    except Exception:
        pass

def _get_user_by_code(code):
    try:
        db = get_db()
        return db.execute("SELECT id, email, name, login_code FROM users WHERE login_code=?", (code,)).fetchone()
    except Exception:
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
        # ADDED: підтримуємо код
        code = (request.form.get("code") or request.form.get("login_code") or "").strip().upper()
        if code:
            _ensure_login_code_column()
            row = _get_user_by_code(code)
            if row:
                r = row if isinstance(row, dict) else dict(row)
                session["user_id"] = r.get("id")
                session["email"] = r.get("email")
                session["name"] = r.get("name")
                session["login_code"] = r.get("login_code")
                flash("Успішний вхід по коду ✅")
                next_url = request.args.get("next") or url_for("index")
                return redirect(next_url)
            flash("Невірний код ❌")
            return redirect(url_for("login"))

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        row = _db_check_password(email, password)
        if row:
            session["user_id"] = row.get("id")
            session["email"] = row.get("email")
            session["name"] = row.get("name")
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
        password = (request.form.get("password") or "")
        if not email or not password:
            flash("Вкажи email і пароль ❌")
            return redirect(url_for("register"))

        uid = _db_create_user(email, name, password)  # якщо БД нема — поверне None

        # ADDED: створюємо довгий код і зберігаємо (якщо є БД/uid)
        _ensure_login_code_column()
        new_code = _gen_code(16)
        if uid:
            _save_code_for_user(uid, new_code)

        # Автологін навіть без БД: тримаємо у сесії
        session["user_id"] = uid
        session["email"] = email
        session["name"] = name
        session["login_code"] = new_code  # показати в профілі/флеші
        flash(f"Реєстрація успішна ✅ Твій код: {new_code}")
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
        password = (request.form.get("password") or "")

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
        except Exception:
            # якщо БД ще не налаштована — не падаємо, просто показуємо повідомлення
            flash("Реєстрація тимчасово без БД — налаштуй DB_PATH/таблицю users. ✅ Форма працює.")
            return redirect(url_for("login"))

    # GET:
    return safe_render("register.html", "Register page (тимчасова заглушка)")

@app.route("/profile")
def profile():
    return render_template("profile.html")

# ===========================
# ✅ ДОДАНО: ендпоінти для профілю, які викликає шаблон
# ===========================
@app.route("/profile/pxp", methods=["POST"])
def profile_pxp():
    user_id = session.get("user_id")
    email = session.get("email")
    try:
        db = get_db()
        if user_id:
            db.execute("UPDATE users SET pxp = COALESCE(pxp,0) + 1 WHERE id = ?", (user_id,))
            db.commit()
            row = db.execute("SELECT pxp FROM users WHERE id = ?", (user_id,)).fetchone()
        elif email:
            db.execute("UPDATE users SET pxp = COALESCE(pxp,0) + 1 WHERE email = ?", (email,))
            db.commit()
            row = db.execute("SELECT pxp FROM users WHERE email = ?", (email,)).fetchone()
        else:
            row = None
        if row:
            pxp_val = (row["pxp"] if not isinstance(row, dict) else row.get("pxp")) or 0
            session["pxp"] = pxp_val
        flash("+1 PXP ✅")
    except Exception:
        session["pxp"] = (session.get("pxp") or 0) + 1
        flash("+1 PXP (session) ✅")
    return redirect(url_for("profile"))

@app.route("/profile/update", methods=["POST"])
def profile_update():
    if not session.get("email") and not session.get("user_id"):
        return redirect(url_for("login"))

    name   = (request.form.get("name") or "").strip() or None
    avatar = (request.form.get("avatar") or "").strip() or None
    bio    = (request.form.get("bio") or "").strip() or None

    try:
        db = get_db()
        if session.get("user_id"):
            db.execute("UPDATE users SET name=?, avatar=?, bio=? WHERE id=?",
                       (name, avatar, bio, session["user_id"]))
        else:
            db.execute("UPDATE users SET name=?, avatar=?, bio=? WHERE email=?",
                       (name, avatar, bio, session["email"]))
        db.commit()
    except Exception:
        pass

    if name:   session["name"] = name
    if avatar: session["avatar"] = avatar
    if bio:    session["bio"] = bio

    flash("Збережено ✅")
    return redirect(url_for("profile"))

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
        if row:
            r = row if isinstance(row, dict) else dict(row)
            if r.get("password") == password:
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

# =========================
# === ADDED FIX (1): створити/знайти юзера після Google і покласти user_id у сесію
# =========================
def ensure_user_in_db_and_session():
    email = session.get("email")
    if not email:
        return
    try:
        db = get_db()
        # якщо запису немає — зробимо апсерт (SQLite/PG)
        row = db.execute("SELECT id, name, avatar, pxp FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            if PSQL_URL:
                db.execute(
                    "INSERT INTO users (email, name, avatar, bio, pxp, name_changes, password) "
                    "VALUES (?, ?, ?, ?, 0, 0, '') ON CONFLICT (email) DO NOTHING",
                    (email, session.get("name"), session.get("avatar"), "")
                )
            else:
                db.execute(
                    "INSERT OR IGNORE INTO users (email, name, avatar, bio, pxp, name_changes, password) "
                    "VALUES (?, ?, ?, ?, 0, 0, '')",
                    (email, session.get("name"), session.get("avatar"), "")
                )
            db.commit()
            row = db.execute("SELECT id, name, avatar, pxp FROM users WHERE email = ?", (email,)).fetchone()

        if row and not session.get("user_id"):
            r = row if isinstance(row, dict) else dict(row)
            session["user_id"] = r.get("id")
            # на всякий випадок — збережемо поточні поля в сесії
            if r.get("name"):   session["name"] = r.get("name")
            if r.get("avatar"): session["avatar"] = r.get("avatar")
            if r.get("pxp") is not None: session["pxp"] = r.get("pxp")
    except Exception:
        pass

@app.before_request
def _autofix_user_session_and_db():
    ensure_user_in_db_and_session()

# =========================
# === ADDED FIX (2): збагачуємо current_user полями pxp та avatar
# =========================
@app.context_processor
def _enrich_current_user_with_stats():
    u = load_current_user()
    # дефолти з сесії
    setattr(u, "avatar", getattr(u, "avatar", None) or session.get("avatar"))
    setattr(u, "pxp",    getattr(u, "pxp", None)    if hasattr(u, "pxp") else session.get("pxp", 0))
    # спробуємо підтягнути з БД
    try:
        db = get_db()
        if getattr(u, "id", None):
            row = db.execute("SELECT avatar, pxp FROM users WHERE id=?", (u.id,)).fetchone()
        elif getattr(u, "email", None):
            row = db.execute("SELECT avatar, pxp FROM users WHERE email=?", (u.email,)).fetchone()
        else:
            row = None
        if row:
            r = row if isinstance(row, dict) else dict(row)
            if r.get("avatar") is not None:
                setattr(u, "avatar", r.get("avatar"))
            if r.get("pxp") is not None:
                setattr(u, "pxp", r.get("pxp"))
    except Exception:
        pass
    # перекриваємо current_user останнім контекстом
    return dict(current_user=u)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)



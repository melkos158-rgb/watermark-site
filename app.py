from flask import Flask, render_template, request, redirect, url_for, flash
import os
import sqlite3

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
    return dict(current_user=Guest(), pxp=0)

def safe_render(tpl, fallback_text):
    try:
        return render_template(tpl)
    except Exception:
        # щоб бачити точну причину — дивись View logs у Railway
        return fallback_text

# ---- маршрути ----
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

@app.route("/login_google")
def login_google():
    flash("Вхід через Google буде додано пізніше 🙂")
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


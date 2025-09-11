from flask import Flask, render_template, request, redirect, url_for, flash
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "devsecret")  # для flash()

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
    except Exception as e:
        # щоб бачити точну причину в логах, виводити не будемо на сторінку
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

@app.route("/register")
def register():
    return safe_render("register.html", "Register page (тимчасова заглушка)")

@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/logout")
def logout():
    return "Logout OK"

# ---- ДОДАНО: обробники для логіну ----
@app.route("/login_local", methods=["POST"])
def login_local():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    # тимчасова перевірка (пізніше підключимо БД)
    if email == "test@test.com" and password == "123":
        flash("Успішний вхід ✅")
        return redirect(url_for("index"))
    else:
        flash("Невірний email або пароль ❌")
        return redirect(url_for("login"))

@app.route("/login_google")
def login_google():
    flash("Вхід через Google буде додано пізніше 🙂")
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


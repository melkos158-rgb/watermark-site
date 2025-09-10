from flask import Flask, render_template, request
import os

app = Flask(__name__)

# ==== Головна ====
@app.route("/")
def index():
    return render_template("index.html")

# ==== Відео ====
@app.route("/video")
def video():
    return render_template("video.html")

# ==== STL (3D-моделі) ====
@app.route("/stl")
def stl():
    return render_template("stl.html")

# ==== Редагування фото ====
@app.route("/edit_photo", methods=["GET", "POST"])
def edit_photo():
    if request.method == "POST":
        # тут ти будеш обробляти завантаження і редагування фото
        pass
    return render_template("edit_photo.html")

# ==== Профіль ====
@app.route("/profile")
def profile():
    return render_template("profile.html")

# ==== Логін ====
@app.route("/login", methods=["GET", "POST"])
def login():
    return render_template("login.html")

# ==== Реєстрація ====
@app.route("/register", methods=["GET", "POST"])
def register():
    return render_template("register.html")

# ==== Тестовий роут (щоб перевіряти роботу швидко) ====
@app.route("/ping")
def ping():
    return "pong"

# ==== Запуск ====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

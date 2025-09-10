import os
from flask import Flask, render_template

# підвантаження .env (для локальної роботи)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# --- маршрути для всіх HTML ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/base")
def base():
    return render_template("base.html")

@app.route("/donate")
def donate():
    return render_template("donate.html")

@app.route("/edit_photo")
def edit_photo():
    return render_template("edit_photo.html")

@app.route("/enhance")
def enhance():
    return render_template("enhance.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/nav")
def nav():
    return render_template("nav.html")

@app.route("/photo")
def photo():
    return render_template("photo.html")

@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/stl")
def stl():
    return render_template("stl.html")

@app.route("/top100")
def top100():
    return render_template("top100.html")

@app.route("/video")
def video():
    return render_template("video.html")

@app.route("/pxp")
def pxp():
    return render_template("PXP.html")


# --- запуск ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)


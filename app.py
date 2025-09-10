from flask import Flask, render_template
import os

app = Flask(__name__)

# --- безпечні дефолти для шаблонів (щоб nav не валив сайт) ---
class Guest:
    is_authenticated = False
    name = None
    email = None

@app.context_processor
def inject_defaults():
    return dict(current_user=Guest(), pxp=0)

# --- маршрути, які є в nav ---
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

@app.route("/top100")
def top100():
    return render_template("top100.html")

@app.route("/donate")
def donate():
    return render_template("donate.html")

@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/logout")
def logout():
    return "Logout OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

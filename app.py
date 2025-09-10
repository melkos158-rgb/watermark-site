from flask import Flask, render_template
import os

app = Flask(__name__)

def safe_render(template, fallback_text):
    try:
        return render_template(template)
    except:
        return fallback_text

@app.route("/")
def index():
    return safe_render("index.html", "Index page OK")

@app.route("/stl")
def stl():
    return safe_render("stl.html", "STL page OK")

@app.route("/video")
def video():
    return safe_render("video.html", "Video page OK")

@app.route("/enhance")
def enhance():
    return safe_render("enhance.html", "Enhance page OK")

@app.route("/edit-photo")
def edit_photo():
    return safe_render("edit_photo.html", "Edit Photo page OK")

@app.route("/top100")
def top100():
    return safe_render("top100.html", "Top100 page OK")

@app.route("/donate")
def donate():
    return safe_render("donate.html", "Donate page OK")

@app.route("/profile")
def profile():
    return safe_render("profile.html", "Profile page OK")

@app.route("/login")
def login():
    return safe_render("login.html", "Login page OK")

@app.route("/register")
def register():
    return safe_render("register.html", "Register page OK")

@app.route("/logout")
def logout():
    return "Logout OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Railway слухає порт 8080
    app.run(host="0.0.0.0", port=port)

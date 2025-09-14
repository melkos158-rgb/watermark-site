# app.py
from flask import Flask, render_template
import os

# наші модулі
from db import close_db
import auth           # auth.bp
import profile        # profile.bp
import chat           # chat.bp  ← для виджета чату

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "devsecret")

    # реєструємо blueprints
    app.register_blueprint(auth.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(chat.bp)

    # коректно закриваємо БД після запиту
    app.teardown_appcontext(close_db)

    # ===== ПУБЛІЧНІ СТОРІНКИ =====
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

    @app.route("/photo")
    def photo():
        return render_template("photo.html")

    # healthcheck для платформи
    @app.route("/healthz")
    def healthz():
        return "ok", 200

    return app


# Gunicorn: `gunicorn app:app`
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))




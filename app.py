# app.py
import os
from flask import Flask, render_template
from db import init_app_db, close_db, db, User  # підключаємо БД тут

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "devsecret-change-me")

    # 1) підключаємо БД до Flask
    init_app_db(app)
    app.teardown_appcontext(close_db)

    # 2) тільки після ініціалізації БД — імпорт і реєстрація blueprints
    import auth           # auth.bp
    import profile        # profile.bp
    import chat           # chat.bp
    app.register_blueprint(auth.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(chat.bp)

    # 3) доступні у всіх шаблонах
    @app.context_processor
    def inject_user():
        from flask import session
        u = User.query.get(session["user_id"]) if session.get("user_id") else None
        return dict(current_user=u, pxp=(u.pxp if u else 0))

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

    # healthcheck
    @app.route("/healthz")
    def healthz():
        return "ok", 200

    return app

# Gunicorn: app:app
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))



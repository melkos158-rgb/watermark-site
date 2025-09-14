from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db

bp = Blueprint("auth", __name__)

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]  # ⚠️ треба хешувати!
        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("INSERT INTO users (email, name, pxp) VALUES (?, ?, 0)", (email, email))
            conn.commit()
        except Exception:
            flash("Користувач уже існує")
            return redirect(url_for("auth.register"))

        cur.exec

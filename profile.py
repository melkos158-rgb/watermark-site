from flask import Blueprint, render_template, redirect, url_for, session, g
from db import get_db

bp = Blueprint("profile", __name__)

def load_user(uid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    return cur.fetchone()

@bp.before_app_request
def attach_user():
    g.user = None
    if "user_id" in session:
        g.user = load_user(session["user_id"])

@bp.context_processor
def inject_user():
    return dict(current_user=g.user)

@bp.route("/profile")
def profile():
    if not g.user:
        return redirect(url_for("auth.login"))
    return render_template("profile.html", user=g.user)

@bp.route("/pxp/plus1", methods=["POST"])
def plus1():
    if not g.user:
        return redirect(url_for("auth.login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET pxp = pxp + 1 WHERE id=?", (g.user["id"],))
    conn.commit()
    session["pxp"] = g.user["pxp"] + 1
    return redirect(url_for("profile.profile"))

@bp.route("/pxp/top")
def top():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, pxp FROM users ORDER BY pxp DESC LIMIT 100")
    leaders = cur.fetchall()
    return render_template("top.html", leaders=leaders)

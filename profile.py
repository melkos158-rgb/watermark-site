from flask import Blueprint, render_template, redirect, url_for, session, g, flash, request, jsonify
from db import get_db

bp = Blueprint("profile", __name__)

# закриті для гостей сторінки
PROTECTED = {"profile.profile", "profile.top", "profile.donate"}

@bp.before_app_request
def gate():
    if request.endpoint in PROTECTED:
        u = g.get("user")
        if not u or not getattr(u, "is_authenticated", False):
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))

@bp.route("/profile")
def profile():
    return render_template("profile.html")

@bp.route("/profile/pxp", methods=["POST"])
def plus1():
    uid = session.get("user_id"); email = session.get("email")
    try:
        db = get_db()
        if uid:
            db.execute("UPDATE users SET pxp = COALESCE(pxp,0) + 1 WHERE id = ?", (uid,))
            db.commit()
            row = db.execute("SELECT pxp FROM users WHERE id = ?", (uid,)).fetchone()
        elif email:
            db.execute("UPDATE users SET pxp = COALESCE(pxp,0) + 1 WHERE email = ?", (email,))
            db.commit()
            row = db.execute("SELECT pxp FROM users WHERE email = ?", (email,)).fetchone()
        else:
            row = None
        if row: session["pxp"] = int((dict(row) if hasattr(row,"keys") else dict(row)).get("pxp") or 0)
        flash("+1 PXP ✅")
    except Exception:
        session["pxp"] = (session.get("pxp") or 0) + 1
        flash("+1 PXP (session) ✅")
    return redirect(url_for("profile.profile"))

@bp.route("/profile/update", methods=["POST"])
def profile_update():
    if not session.get("email") and not session.get("user_id"):
        return redirect(url_for("auth.login"))
    name   = (request.form.get("name") or "").strip() or None
    avatar = (request.form.get("avatar") or "").strip() or None  # dataURL або URL
    bio    = (request.form.get("bio") or "").strip() or None
    try:
        db = get_db()
        if session.get("user_id"):
            db.execute("UPDATE users SET name=?, avatar=?, bio=? WHERE id=?",
                       (name, avatar, bio, session["user_id"]))
        else:
            db.execute("UPDATE users SET name=?, avatar=?, bio=? WHERE email=?",
                       (name, avatar, bio, session["email"]))
        db.commit()
    except Exception:
        pass
    if name:   session["name"]=name
    if avatar: session["avatar"]=avatar
    if bio:    session["bio"]=bio
    flash("Збережено ✅")
    return redirect(url_for("profile.profile"))

@bp.route("/top100")
def top():
    return render_template("top100.html")

@bp.route("/api/pxp/top100")
def api_top100():
    db = get_db()
    cur = db.execute("""
        SELECT id, COALESCE(name,'Без імені') AS name, email, COALESCE(pxp,0) AS pxp
        FROM users ORDER BY pxp DESC, id ASC LIMIT 100
    """)
    rows = cur.fetchall()
    data = [dict(r) if hasattr(r,"keys") else dict(r) for r in rows]
    return jsonify(data)

@bp.route("/donate")
def donate():
    return render_template("donate.html")

from flask import Blueprint, render_template, redirect, url_for, session, g, flash, request, jsonify
from db import get_db

bp = Blueprint("profile", __name__)

@bp.route("/top100")
def top():
    # рендеримо сторінку; дані підтягне JS з API
    return render_template("top100.html")

@bp.route("/api/pxp/top100")
def api_top100():
    db = get_db()
    cur = db.execute("""
        SELECT id,
               COALESCE(name, 'Без імені') AS name,
               email,
               COALESCE(pxp, 0)            AS pxp
        FROM users
        ORDER BY pxp DESC, id ASC
        LIMIT 100
    """)
    rows = cur.fetchall()

    # робимо список словників (щоб jsonify нормально спрацював)
    data = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else dict(r)
        data.append({
            "id": d.get("id"),
            "name": d.get("name"),
            "email": d.get("email"),
            "pxp": int(d.get("pxp") or 0)
        })
    return jsonify(data)

    cur.execute("SELECT id, name, email, pxp FROM users ORDER BY pxp DESC LIMIT 100")
    leaders = cur.fetchall()
    return render_template("top.html", leaders=leaders)

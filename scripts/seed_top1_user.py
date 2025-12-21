import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
app = create_app()

with app.app_context():
    # ВАЖЛИВО: імпортуй User З ТОГО Ж МОДУЛЯ, що і ads.py
    import ads
    User = ads.User
    db = ads.db

    u = User.query.order_by(User.id.asc()).first()
    if not u:
        u = User()
        # мінімальні поля — підстав те, що у твоїй моделі реально існує
        if hasattr(u, "email"): u.email = "test@local.dev"
        if hasattr(u, "password"): u.password = "test"
        if hasattr(u, "username"): u.username = "test"
        db.session.add(u)
        db.session.commit()
        print("created user id=", u.id)
    else:
        print("existing user id=", u.id)

    # зробити TOP-1
    if hasattr(u, "pxp_month"):
        u.pxp_month = 999999
    if hasattr(u, "pxp"):
        u.pxp = 999999
    db.session.commit()
    print("made top1 user id=", u.id)

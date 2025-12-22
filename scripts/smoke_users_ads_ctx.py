import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app

app = create_app()

with app.app_context():
    import ads
    from db import User

    u1 = User.query.get(1)
    print("User(1) exists:", bool(u1))
    print("User(1) email:", getattr(u1, "email", None))

    rows = User.query.order_by(User.id.asc()).limit(10).all()
    print("first10:", [(u.id, getattr(u,"email",None), getattr(u,"pxp",None), getattr(u,"pxp_month",None)) for u in rows])

    top = ads.get_top1_user_this_month()
    print("top1:", None if not top else (top.id, getattr(top,"email",None), getattr(top,"pxp",None), getattr(top,"pxp_month",None)))

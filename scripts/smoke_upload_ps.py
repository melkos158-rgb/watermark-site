import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app

app = create_app()
app.testing = True
c = app.test_client()

print("\n=== BLUEPRINTS ===")
print(sorted(app.blueprints.keys()))

print("\n=== ROUTES: draft/upload ===")
for r in app.url_map.iter_rules():
    if ("items/draft" in r.rule) or (r.rule == "/api/market/upload") or (("upload" in r.rule) and r.rule.startswith("/api/market/")):
        print(f"{r.rule:55s} -> {r.endpoint} {sorted(r.methods)}")

def show_resp(label, r):
    print(f"\n--- {label} ---")
    print("status:", r.status_code)
    ct = r.headers.get("content-type")
    print("content-type:", ct)
    try:
        print("json:", r.get_json())
    except Exception:
        print("body:", (r.data or b"")[:400])

print("\n=== 0) ping ===")
show_resp("GET /api/market/ping", c.get("/api/market/ping"))

print("\n=== 1) draft WITHOUT auth ===")
r = c.post("/api/market/items/draft")
show_resp("POST /api/market/items/draft", r)

print("\n=== 2) set session user_id=1 and draft again ===")
with c.session_transaction() as s:
    s["user_id"] = 1
r2 = c.post("/api/market/items/draft")
show_resp("POST /api/market/items/draft (session user_id=1)", r2)

print("\n=== 3) session dump ===")
with c.session_transaction() as s:
    print(dict(s))

print("\n=== 4) upload (empty) ===")
r3 = c.post("/api/market/upload", data={})
show_resp("POST /api/market/upload (empty)", r3)

print("\n=== DONE ===")

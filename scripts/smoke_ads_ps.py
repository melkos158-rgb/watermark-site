import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app

app = create_app()
app.testing = True
c = app.test_client()

def show(label, r):
    print(f"\n--- {label} ---")
    print("status:", r.status_code)
    print("location:", r.headers.get("location"))
    print("content-type:", r.headers.get("content-type"))
    body = (r.data or b"")[:300]
    if body:
        print("body:", body)

print("=== 0) GET /ad/upload (NO AUTH) ===")
show("GET /ad/upload", c.get("/ad/upload", follow_redirects=False))

print("\n=== 1) POST /ad/upload (NO AUTH, empty) ===")
show("POST /ad/upload", c.post("/ad/upload", data={}, follow_redirects=False))

print("\n=== 2) SET session user_id=1 ===")
with c.session_transaction() as s:
    s["user_id"] = 1
print("session set: user_id=1")

print("\n=== 3) GET /ad/upload (AUTH) ===")
show("GET /ad/upload (auth)", c.get("/ad/upload", follow_redirects=False))

print("\n=== 4) POST /ad/upload (AUTH, empty) ===")
show("POST /ad/upload (auth, empty)", c.post("/ad/upload", data={}, follow_redirects=False))

print("\n=== DONE ===")

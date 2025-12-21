import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import io
from datetime import datetime
from app import create_app

def show(label, resp):
    print(f"\n--- {label} ---")
    print("status:", resp.status_code)
    loc = resp.headers.get("Location")
    if loc:
        print("location:", loc)
    print("content-type:", resp.headers.get("Content-Type"))
    print("body[0:220]:", resp.get_data()[:220])

def png_bytes_1x1():
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
        b"\xe2!\xbc3"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

app = create_app()
app.config["TESTING"] = True
user_id = int(os.getenv("SMOKE_USER_ID", "1"))

with app.test_client() as c:
    print("=== 0) GET /ad/upload (NO AUTH) ===")
    r = c.get("/ad/upload", follow_redirects=False)
    show("GET /ad/upload (no auth)", r)

    print("\n=== 1) POST /ad/upload (NO AUTH, empty) ===")
    r = c.post("/ad/upload", data={}, follow_redirects=False)
    show("POST /ad/upload (no auth)", r)

    print("\n=== 2) SET session user_id ===")
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
    print("session set: user_id=", user_id)

    print("\n=== 3) GET /ad/upload (AUTH) ===")
    r = c.get("/ad/upload", follow_redirects=False)
    show("GET /ad/upload (auth)", r)

    print("\n=== 4) POST /ad/upload (AUTH + image) ===")
    fname = f"smoke_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
    data = {
        "link_url": "https://proofly.store/market",
        "image": (io.BytesIO(png_bytes_1x1()), fname),
    }
    r = c.post("/ad/upload", data=data, content_type="multipart/form-data", follow_redirects=False)
    show("POST /ad/upload (auth + image)", r)

print("\n✅ DONE")

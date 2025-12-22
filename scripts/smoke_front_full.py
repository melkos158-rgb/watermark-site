import io
from datetime import datetime, timezone

from app import create_app


def show(method, url, r):
    print(f"{method} {url} -> {r.status_code} "
          f"ct={r.headers.get('Content-Type')} "
          f"loc={r.headers.get('Location')}")
    body = r.get_data()[:160]
    if body:
        print("body0:", body)

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

print("=== CREATE APP ===")
app = create_app()
client = app.test_client()
print("OK APP")

print("\n=== NO AUTH GET ===")
for url in [
    "/", "/market", "/market/upload", "/ad/upload",
    "/api/items", "/api/market/ping", "/api/lang/me"
]:
    show("GET", url, client.get(url, follow_redirects=False))

print("\n=== POST draft (NO AUTH, expect 401) ===")
show("POST", "/api/market/items/draft",
     client.post("/api/market/items/draft", json={}, follow_redirects=False))

print("\n=== SET session user_id=1 ===")
with client.session_transaction() as sess:
    sess["user_id"] = 1
print("session user_id=1")

print("\n=== POST draft (AUTH) ===")
show("POST", "/api/market/items/draft",
     client.post("/api/market/items/draft", json={}, follow_redirects=False))

print("\n=== ADS upload (AUTH + image) ===")
show("GET", "/ad/upload", client.get("/ad/upload", follow_redirects=False))

fname = f"smoke_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
data = {
    "link_url": "https://proofly.store/market",
    "image": (io.BytesIO(png_bytes_1x1()), fname),
}
show("POST", "/ad/upload",
     client.post("/ad/upload", data=data,
                 content_type="multipart/form-data",
                 follow_redirects=False))

print("\n✅ DONE")

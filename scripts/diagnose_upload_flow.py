# scripts/diagnose_upload_flow.py
import io
from datetime import datetime, timezone

from app import create_app


def head(txt: str):
    print("\n" + "=" * 70)
    print(txt)
    print("=" * 70)


def show(method: str, url: str, r):
    ct = r.headers.get("Content-Type")
    loc = r.headers.get("Location")
    print(f"{method:>4} {url:<30} -> {r.status_code} ct={ct} loc={loc}")
    b = r.get_data()[:200]
    if b:
        print("body0:", b)


def tiny_png_bytes() -> bytes:
    # 1x1 transparent PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00"
        b"\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def main():
    head("0) CREATE APP")
    app = create_app()
    c = app.test_client()
    print("OK APP")

    head("1) ROUTE CHECK (must exist)")
    must = [
        ("GET", "/market/upload"),
        ("POST", "/api/market/items/draft"),
        ("POST", "/api/market/upload"),
        ("GET", "/item/1"),
    ]
    { (next(iter(sorted(r.methods - {"HEAD", "OPTIONS"}))), r.rule): r.endpoint
              for r in app.url_map.iter_rules() if r.endpoint != "static" }
    # Build a quick "exists" check by scanning all rules
    all_rules = [(sorted(list(r.methods)), r.rule, r.endpoint) for r in app.url_map.iter_rules()]
    for method, path in must:
        exists = any((method in mset and rule == path) for (mset, rule, _ep) in all_rules)
        print(f"{method} {path} -> {'OK' if exists else 'MISSING'}")

    head("2) NO AUTH SMOKE")
    for u in ["/", "/market", "/market/upload", "/api/items", "/api/market/ping", "/api/lang/me"]:
        r = c.get(u, follow_redirects=False)
        show("GET", u, r)

    head("3) DRAFT (NO AUTH) expect 401")
    r = c.post("/api/market/items/draft", json={}, follow_redirects=False)
    show("POST", "/api/market/items/draft", r)

    head("4) AUTH as session user_id=1")
    with c.session_transaction() as s:
        s["user_id"] = 1
    print("session user_id=1")

    head("5) DRAFT (AUTH) expect 200 + draft id")
    r = c.post("/api/market/items/draft", json={}, follow_redirects=False)
    show("POST", "/api/market/items/draft", r)

    # parse draft id if possible
    draft_id = None
    try:
        js = r.get_json(silent=True) or {}
        draft_id = (js.get("draft") or {}).get("id")
    except Exception:
        draft_id = None
    print("draft_id =", draft_id)

    head("6) UPLOAD (AUTH) send minimal multipart with png")
    png = tiny_png_bytes()
    fname = f"diag_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"

    # IMPORTANT: field names must match your backend handler.
    # We try common ones: "cover", then "image", then "file".
    candidates = ["cover", "image", "file"]

    # Minimal text fields — if your API requires more, you will see 400 and body0.
    base_form = {
        "title": "Diag upload",
        "price": "0",
        "is_free": "1",
    }
    if draft_id is not None:
        base_form["draft_id"] = str(draft_id)

    last = None
    for field in candidates:
        data = dict(base_form)
        data[field] = (io.BytesIO(png), fname)
        r = c.post(
            "/api/market/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        print(f"\n--- try file field '{field}' ---")
        show("POST", "/api/market/upload", r)
        last = r
        if r.status_code not in (400, 404, 415):
            break

    head("7) WHAT HAPPENS AFTER UPLOAD")
    if last is not None:
        # If JSON returned, try to extract item_id and check GET /item/<id>
        js = last.get_json(silent=True) or {}
        item_id = js.get("item_id") or (js.get("item") or {}).get("id")
        print("upload json:", js if js else "(no json)")
        if item_id:
            r = c.get(f"/item/{item_id}", follow_redirects=False)
            show("GET", f"/item/{item_id}", r)
        else:
            print("No item_id in JSON; check redirect Location or response body above.")

    head("DONE")


if __name__ == "__main__":
    main()

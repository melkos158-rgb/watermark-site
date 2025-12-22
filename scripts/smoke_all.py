# scripts/smoke_all.py
import io
import os
import sys
import traceback
from datetime import datetime, timezone


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

def safe_print(s: str):
    try:
        print(s)
    except Exception:
        # very rare windows console encoding weirdness
        print(s.encode("utf-8", "ignore").decode("utf-8", "ignore"))

def show_resp(label, resp):
    loc = resp.headers.get("Location")
    ct = resp.headers.get("Content-Type")
    body = resp.get_data()[:220]
    safe_print(f"{label}: {resp.status_code} ct={ct} loc={loc} body0={body!r}")

def main():
    # 0) Import app
    safe_print("=== 0) IMPORT create_app ===")
    try:
        from app import create_app
    except Exception:
        safe_print("❌ FAILED: from app import create_app")
        traceback.print_exc()
        sys.exit(2)

    # 1) Create app
    safe_print("\n=== 1) CREATE APP ===")
    try:
        app = create_app()
        app.config["TESTING"] = True
        safe_print("✅ APP CREATED")
    except Exception:
        safe_print("❌ FAILED: create_app()")
        traceback.print_exc()
        sys.exit(2)

    # 2) Import models
    safe_print("\n=== 2) IMPORT models ===")
    try:
        import models  # noqa: F401
        safe_print("✅ MODELS IMPORTED")
    except Exception:
        safe_print("❌ FAILED: import models")
        traceback.print_exc()
        # keep going

    # 3) Blueprints
    safe_print("\n=== 3) BLUEPRINTS ===")
    for k in sorted(app.blueprints.keys()):
        safe_print(f" - {k}")

    # 4) Routes (short summary)
    safe_print("\n=== 4) ROUTE SANITY (key endpoints must exist) ===")
    want = [
        ("GET", "/"),
        ("GET", "/market"),
        ("GET", "/market/upload"),
        ("GET", "/item/1"),  # may 404 if item doesn't exist; still ok
        ("GET", "/api/items"),
        ("POST", "/api/market/items/draft"),
        ("POST", "/api/market/upload"),
        ("GET", "/ad/upload"),
        ("POST", "/ad/upload"),
    ]

    # Build a quick set of (method, rule)
    rules = list(app.url_map.iter_rules())
    have = set()
    for r in rules:
        for m in r.methods:
            have.add((m, r.rule))

    missing = []
    for m, path in want:
        # ignore /item/1 exact match (it's a variable rule)
        if path == "/item/1":
            ok = any((m in rr.methods and rr.rule.startswith("/item/")) for rr in rules)
        else:
            ok = (m, path) in have
        if not ok:
            missing.append((m, path))
    if missing:
        safe_print("❌ MISSING ROUTES:")
        for m, p in missing:
            safe_print(f" - {m} {p}")
    else:
        safe_print("✅ Key routes exist")

    # 5) Jinja template compile check (best-effort)
    safe_print("\n=== 5) JINJA COMPILE CHECK (best-effort) ===")
    try:
        env = app.jinja_env
        # Compile every template found by loader
        # Not all loaders support list_templates; try safely
        names = []
        try:
            names = env.list_templates()
        except Exception:
            names = []
        if not names:
            safe_print("ℹ️ list_templates() not available or empty; skipping full compile")
        else:
            bad = []
            for name in names:
                try:
                    env.get_template(name)
                except Exception as e:
                    bad.append((name, str(e)))
            if bad:
                safe_print(f"❌ BAD TEMPLATES: {len(bad)}")
                for name, err in bad[:30]:
                    safe_print(f" - {name}: {err}")
            else:
                safe_print(f"✅ Templates compiled: {len(names)}")
    except Exception:
        safe_print("⚠️ Template check crashed (ignored)")
        traceback.print_exc()

    # 6) HTTP smoke via test_client (NO AUTH)
    safe_print("\n=== 6) HTTP SMOKE (NO AUTH) ===")
    c = app.test_client()

    get_eps = [
        "/",
        "/market",
        "/market/upload",
        "/ad/upload",
        "/api/items",
        "/api/market/ping",
        "/api/lang/me",
    ]
    for e in get_eps:
        try:
            r = c.get(e, follow_redirects=False)
            show_resp(f"GET {e}", r)
        except Exception:
            safe_print(f"❌ GET {e} crashed")
            traceback.print_exc()

    # POST checks (NO AUTH)
    post_eps = [
        ("/api/market/items/draft", {"title": "smoke"}),
    ]
    for e, payload in post_eps:
        try:
            r = c.post(e, json=payload, follow_redirects=False)
            show_resp(f"POST {e}", r)
            # Allow 401 as OK for endpoints that require auth
            if e in ["/api/market/items/draft", "/api/market/upload"] and r.status_code == 401:
                safe_print(f"✅ POST {e} returned 401 (expected for no-auth)")
            elif r.status_code >= 400:
                safe_print(f"❌ POST {e} failed: {r.status_code}")
        except Exception:
            safe_print(f"❌ POST {e} crashed")
            traceback.print_exc()

    # 7) Ads upload smoke (AUTH session user_id) with tiny png
    safe_print("\n=== 7) ADS UPLOAD SMOKE (AUTH) ===")
    user_id = int(os.getenv("SMOKE_USER_ID", "1"))
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
    safe_print(f"session user_id={user_id}")

    try:
        r = c.get("/ad/upload", follow_redirects=False)
        show_resp("GET /ad/upload (auth)", r)
    except Exception:
        safe_print("❌ GET /ad/upload (auth) crashed")
        traceback.print_exc()

    try:
        fname = f"smoke_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
        data = {
            "link_url": "https://proofly.store/market",
            "image": (io.BytesIO(png_bytes_1x1()), fname),
        }
        r = c.post("/ad/upload", data=data, content_type="multipart/form-data", follow_redirects=False)
        show_resp("POST /ad/upload (auth + image)", r)
    except Exception:
        safe_print("❌ POST /ad/upload (auth + image) crashed")
        traceback.print_exc()

    safe_print("\n✅ SMOKE_ALL DONE")

if __name__ == "__main__":
    main()


import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app


def main():
    app = create_app()
    app.testing = True
    c = app.test_client()

    def jprint(name, resp):
        ct = resp.headers.get("content-type", "")
        body = resp.get_data(as_text=True)
        print(f"\n=== {name} ===")
        print("status:", resp.status_code)
        print("content-type:", ct)
        if "application/json" in ct:
            try:
                print(json.dumps(resp.get_json(), indent=2, ensure_ascii=False))
            except Exception:
                print(body[:800])
        else:
            print(body[:800])

    # 1) Ping
    r = c.get("/api/market/ping")
    jprint("GET /api/market/ping", r)


    # 2) Draft create (set user_id in session)
    with c.session_transaction() as sess:
        sess["user_id"] = 1
    r = c.post("/api/market/items/draft")
    jprint("POST /api/market/items/draft", r)

    data = r.get_json(silent=True) or {}
    draft_id = ((data.get("draft") or {}).get("id") or 0)
    if not isinstance(draft_id, int) or draft_id <= 0:
        raise SystemExit(f"\nFAIL: draft_id is invalid: {draft_id!r} (must be int > 0)")

    # 3) Check key routes exist
    rules = sorted([rule.rule for rule in app.url_map.iter_rules()])
    must = [
        "/api/market/items/draft",
        "/api/market/items/<int:item_id>/upload/<file_type>",
        "/api/market/items/<int:item_id>/attach",
    ]
    missing = [m for m in must if not any(r.startswith(m.split("<")[0]) for r in rules)]
    if missing:
        raise SystemExit(f"\nFAIL: missing routes: {missing}")

    print(f"\nOK: draft_id={draft_id} and required routes exist.")

if __name__ == "__main__":
    main()

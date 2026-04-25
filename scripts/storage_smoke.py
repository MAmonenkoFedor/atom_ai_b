import json
import uuid

import requests

BASE = "http://127.0.0.1:8000/api/v1"


def main() -> None:
    s = requests.Session()
    r = s.get(f"{BASE}/auth/csrf", timeout=10)
    assert r.status_code == 200, r.text

    def headers() -> dict[str, str]:
        return {
            "Referer": "http://127.0.0.1:8000/",
            "X-CSRFToken": s.cookies.get("csrftoken", ""),
            "Content-Type": "application/json",
        }

    r = s.post(
        f"{BASE}/auth/login",
        data=json.dumps({"username": "super_admin_test", "password": "Pass12345!"}),
        headers=headers(),
        timeout=10,
    )
    assert r.status_code == 200, r.text

    r = s.get(f"{BASE}/super-admin/storage/usage", timeout=10)
    assert r.status_code == 200, r.text
    usage = r.json()
    assert "total_bytes" in usage
    print("usage ok", usage.get("total_bytes"))

    r = s.get(f"{BASE}/super-admin/storage/quotas?page_size=10", timeout=10)
    assert r.status_code == 200, r.text
    payload = r.json()
    print("list ok", payload.get("total", 0))
    items = payload.get("items") or []
    if items and isinstance(items[0], dict):
        row0 = items[0]
        assert "source_label" in row0, "quota row should include source_label"
        assert "remaining_bytes" in row0, "quota row should include remaining_bytes"
        assert "remaining_after_upload" in row0, "quota row should include remaining_after_upload (nullable)"
        r_inc = s.get(
            f"{BASE}/super-admin/storage/quotas?page_size=1&incoming_bytes=1024",
            timeout=10,
        )
        assert r_inc.status_code == 200, r_inc.text
        inc_items = (r_inc.json() or {}).get("items") or []
        if inc_items and isinstance(inc_items[0], dict):
            assert inc_items[0].get("remaining_after_upload") is not None, (
                "with incoming_bytes, remaining_after_upload should be present"
            )

    suffix = uuid.uuid4().hex[:8]
    created_this_run = False
    prev_notes = ""
    r = s.post(
        f"{BASE}/super-admin/storage/quotas",
        data=json.dumps(
            {
                "scope": "global",
                "max_bytes": 9_999_999_999,
                "warn_bytes": 1_000_000_000,
                "is_active": True,
                "notes": f"smoke global {suffix}",
            }
        ),
        headers=headers(),
        timeout=10,
    )
    if r.status_code == 409:
        print("global quota already exists, reusing for patch-only", r.text[:200])
        r = s.get(f"{BASE}/super-admin/storage/quotas?scope=global&page_size=1", timeout=10)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or []
        assert items, "expected at least one global quota"
        quota_id = items[0]["id"]
        prev_notes = (items[0].get("notes") or "") if isinstance(items[0], dict) else ""
    else:
        assert r.status_code == 201, (r.status_code, r.text)
        created = r.json()
        quota_id = created["id"]
        created_this_run = True
        print("create ok", created.get("scope"), created.get("max_bytes"))

    r = s.patch(
        f"{BASE}/super-admin/storage/quotas/{quota_id}",
        data=json.dumps({"notes": f"smoke patched {suffix}", "is_active": True}),
        headers=headers(),
        timeout=10,
    )
    assert r.status_code == 200, (r.status_code, r.text)
    print("patch ok", r.json().get("notes", "")[:40])

    if created_this_run:
        r = s.delete(
            f"{BASE}/super-admin/storage/quotas/{quota_id}",
            headers=headers(),
            timeout=10,
        )
        assert r.status_code == 204, (r.status_code, r.text)
        print("delete ok (created in this run)")
    elif prev_notes:
        r = s.patch(
            f"{BASE}/super-admin/storage/quotas/{quota_id}",
            data=json.dumps({"notes": prev_notes}),
            headers=headers(),
            timeout=10,
        )
        assert r.status_code == 200, (r.status_code, r.text)
        print("restored notes on pre-existing global quota")
    else:
        print("skip delete / restore (pre-existing global quota, no prior notes)")

    r = s.post(f"{BASE}/auth/logout", headers=headers(), timeout=10)
    assert r.status_code == 204, r.status_code
    print("SMOKE STORAGE OK")


if __name__ == "__main__":
    main()

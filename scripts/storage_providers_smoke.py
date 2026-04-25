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

    r = s.get(f"{BASE}/super-admin/storage/providers?page_size=10", timeout=10)
    assert r.status_code == 200, r.text
    print("list ok", r.json().get("total", 0))

    suffix = uuid.uuid4().hex[:6]
    code = f"smoke_{suffix}"
    r = s.post(
        f"{BASE}/super-admin/storage/providers",
        data=json.dumps(
            {
                "code": code,
                "name": "Smoke S3",
                "kind": "s3_compat",
                "is_active": True,
                "is_default": False,
                "priority": 50,
                "endpoint_url": "http://127.0.0.1:9000",
                "bucket": "atom-ai",
                "region": "",
                "use_ssl": False,
                "path_style": True,
                "access_key": "minioadmin",
                "secret_key": "minioadmin",
            }
        ),
        headers=headers(),
        timeout=10,
    )
    assert r.status_code == 201, (r.status_code, r.text)
    pid = r.json()["id"]
    print("create ok", code, pid)

    r = s.patch(
        f"{BASE}/super-admin/storage/providers/{pid}",
        data=json.dumps({"name": "Smoke S3 Updated", "priority": 51}),
        headers=headers(),
        timeout=10,
    )
    assert r.status_code == 200, (r.status_code, r.text)

    r = s.post(
        f"{BASE}/super-admin/storage/providers/{pid}/probe",
        headers=headers(),
        timeout=30,
    )
    assert r.status_code == 200, (r.status_code, r.text)
    body = r.json()
    print("probe", body.get("ok"), body.get("latency_ms"), body.get("message", "")[:80])

    r = s.delete(f"{BASE}/super-admin/storage/providers/{pid}", headers=headers(), timeout=10)
    assert r.status_code == 204, (r.status_code, r.text)

    r = s.post(f"{BASE}/auth/logout", headers=headers(), timeout=10)
    assert r.status_code == 204, r.status_code
    print("SMOKE STORAGE PROVIDERS OK")


if __name__ == "__main__":
    main()

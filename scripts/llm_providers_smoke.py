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

    r = s.get(f"{BASE}/super-admin/llm/providers?page_size=5", timeout=10)
    assert r.status_code == 200, r.text
    print("list ok", len(r.json().get("items", [])))

    code = "smoke_" + uuid.uuid4().hex[:8]
    r = s.post(
        f"{BASE}/super-admin/llm/providers",
        data=json.dumps(
            {
                "code": code,
                "name": "Smoke Provider",
                "priority": 77,
                "mock_override": True,
                "api_key": "secret123",
                "base_url_override": "https://example.test/v1",
            }
        ),
        headers=headers(),
        timeout=10,
    )
    assert r.status_code == 201, (r.status_code, r.text)
    created = r.json()
    provider_id = created["id"]
    assert created["has_secret"] is True
    print("create ok", created["code"], created["has_secret"])

    r = s.patch(
        f"{BASE}/super-admin/llm/providers/{provider_id}",
        data=json.dumps({"name": "Smoke Provider Updated", "mock_override": False}),
        headers=headers(),
        timeout=10,
    )
    assert r.status_code == 200, (r.status_code, r.text)
    print("patch ok", r.json()["name"], r.json()["mock_override"])

    r = s.post(
        f"{BASE}/super-admin/llm/providers/{provider_id}/probe",
        headers=headers(),
        timeout=10,
    )
    assert r.status_code == 400, (r.status_code, r.text)
    print("probe expected validation", r.status_code)

    r = s.delete(
        f"{BASE}/super-admin/llm/providers/{provider_id}",
        headers=headers(),
        timeout=10,
    )
    assert r.status_code == 204, (r.status_code, r.text)
    print("delete ok")

    r = s.post(f"{BASE}/auth/logout", headers=headers(), timeout=10)
    assert r.status_code == 204, r.status_code
    print("SMOKE LLM PROVIDERS OK")


if __name__ == "__main__":
    main()

"""Smoke: authenticated project + workspace document uploads (multipart).

Expects a running API (default http://127.0.0.1:8000/api/v1) and seeded users with
project membership — e.g. ``python manage.py seed_alignment_demo_data``.

Uses session cookies + CSRF like other smoke scripts.
"""

from __future__ import annotations

import io
import json
import sys
import uuid

import requests

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"
PASSWORD = "Pass12345!"


def expect(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)


def _login_candidates() -> list[tuple[str, str]]:
    """Prefer demo users with editor/owner on a project."""
    return [
        ("employee_demo_1", PASSWORD),
        ("manager_demo", PASSWORD),
        ("company_admin_test", PASSWORD),
        ("employee_test", PASSWORD),
    ]


def _projects_rows(data: object) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("results", "items", "projects"):
            raw = data.get(key)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
    return []


def main() -> None:
    session = requests.Session()
    r = session.get(f"{API}/auth/csrf", timeout=10)
    expect(r.status_code == 200, f"csrf -> {r.status_code}")
    csrf = session.cookies.get("csrftoken")
    expect(bool(csrf), "csrftoken cookie")

    def json_headers() -> dict[str, str]:
        return {
            "Referer": BASE + "/",
            "X-CSRFToken": session.cookies.get("csrftoken", ""),
            "Content-Type": "application/json",
        }

    logged = False
    username = ""
    for user, pwd in _login_candidates():
        r = session.post(
            f"{API}/auth/login",
            data=json.dumps({"username": user, "password": pwd}),
            headers=json_headers(),
            timeout=15,
        )
        if r.status_code == 200:
            logged = True
            username = user
            break

    expect(logged, f"login failed for all candidates (last status {r.status_code}): {r.text[:240]}")

    r = session.get(f"{API}/projects?scope=member_of&page_size=20", headers=json_headers(), timeout=15)
    expect(r.status_code == 200, f"projects list -> {r.status_code}: {r.text[:300]}")
    rows = _projects_rows(r.json())
    if not rows:
        print(
            "SKIP document_upload_smoke: no projects for member_of scope.\n"
            "  Run: python manage.py seed_alignment_demo_data",
        )
        session.post(f"{API}/auth/logout", headers=json_headers(), timeout=10)
        return

    pid = rows[0].get("id")
    expect(pid is not None, "project id missing in list row")

    suffix = uuid.uuid4().hex[:10]
    buf = io.BytesIO(f"smoke-upload-{suffix}\n".encode("utf-8"))
    files = {"file": (f"smoke-{suffix}.txt", buf, "text/plain")}
    upload_headers = {
        "Referer": BASE + "/",
        "X-CSRFToken": session.cookies.get("csrftoken", ""),
    }
    r = session.post(
        f"{API}/projects/{int(pid)}/documents/upload",
        files=files,
        headers=upload_headers,
        timeout=60,
    )
    expect(r.status_code == 201, f"project upload -> {r.status_code}: {r.text[:500]}")
    body = r.json()
    expect(isinstance(body, dict) and body.get("id") is not None, "upload response should include id")

    buf2 = io.BytesIO(f"workspace-cabinet-{suffix}\n".encode("utf-8"))
    files2 = {"file": (f"ws-smoke-{suffix}.txt", buf2, "text/plain")}
    r = session.post(
        f"{API}/workspace/documents/upload",
        files=files2,
        headers=upload_headers,
        timeout=60,
    )
    expect(r.status_code == 201, f"workspace upload -> {r.status_code}: {r.text[:500]}")
    ws_body = r.json()
    expect(isinstance(ws_body, dict) and ws_body.get("id") is not None, "workspace upload should include id")

    session.post(f"{API}/auth/logout", headers=json_headers(), timeout=10)
    print(f"DOCUMENT_UPLOAD_SMOKE OK (user={username}, project_id={pid})")


if __name__ == "__main__":
    main()

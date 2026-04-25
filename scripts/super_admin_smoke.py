"""Super-admin & audit smoke pass.

Runs against a live dev server. Uses requests + session cookies.

Flow:
1. Prime CSRF cookie.
2. Login as super_admin_test.
3. GET /me/capabilities (expect bundle for super_admin).
4. GET /super-admin/capabilities (catalog).
5. GET /super-admin/users (list).
6. POST /super-admin/users/invite (ephemeral email).
7. PATCH /super-admin/users/<new>/roles (set employee).
8. PATCH /super-admin/users/<new>/capabilities (add audit.view_all).
9. POST /super-admin/users/<new>/disable.
10. POST /super-admin/users/<new>/enable.
11. GET /audit/events (check we emit events).
12. GET /audit/stats.
13. GET /audit/events/export (CSV).
14. POST /auth/logout.
"""

from __future__ import annotations

import json
import sys
import time
import uuid

import requests

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"

PASSWORD = "Pass12345!"


def headline(name: str) -> None:
    print(f"\n--- {name}")


def expect(cond: bool, msg: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"    [{status}] {msg}")
    if not cond:
        print("    ABORT")
        sys.exit(1)


def main() -> None:
    session = requests.Session()

    headline("1. prime CSRF cookie")
    r = session.get(f"{API}/auth/csrf", timeout=10)
    expect(r.status_code == 200, f"/auth/csrf -> {r.status_code}")
    csrf = session.cookies.get("csrftoken")
    expect(bool(csrf), "csrftoken cookie present")

    def auth_headers() -> dict:
        return {
            "Referer": BASE,
            "X-CSRFToken": session.cookies.get("csrftoken", ""),
            "Content-Type": "application/json",
        }

    headline("2. login super_admin_test")
    r = session.post(
        f"{API}/auth/login",
        data=json.dumps({"username": "super_admin_test", "password": PASSWORD}),
        headers=auth_headers(),
        timeout=10,
    )
    expect(r.status_code == 200, f"/auth/login -> {r.status_code} body={r.text[:200]}")
    body = r.json()
    user_payload = body.get("session", {}).get("user", {})
    expect(
        user_payload.get("role") == "super_admin",
        f"session.user.role=super_admin (got {user_payload.get('role')})",
    )

    headline("3. GET /me/capabilities")
    r = session.get(f"{API}/me/capabilities", timeout=10)
    expect(r.status_code == 200, f"/me/capabilities -> {r.status_code}")
    me_payload = r.json()
    caps = me_payload.get("capabilities") if isinstance(me_payload, dict) else me_payload
    print(f"    capabilities count: {len(caps)}")
    expect("users.view_all" in caps, "super_admin has users.view_all")
    expect("audit.view_all" in caps, "super_admin has audit.view_all")
    expect("roles.manage" in caps, "super_admin has roles.manage")

    headline("4. GET /super-admin/capabilities (catalog)")
    r = session.get(f"{API}/super-admin/capabilities", timeout=10)
    expect(r.status_code == 200, f"/super-admin/capabilities -> {r.status_code}")
    catalog = r.json()
    expect(isinstance(catalog.get("capabilities"), list), "catalog.capabilities is list")
    expect(isinstance(catalog.get("roles"), list), "catalog.roles is list")
    print(f"    catalog caps={len(catalog['capabilities'])} roles={len(catalog['roles'])}")

    headline("5. GET /super-admin/users")
    r = session.get(f"{API}/super-admin/users?page_size=5", timeout=10)
    expect(r.status_code == 200, f"/super-admin/users -> {r.status_code}")
    listing = r.json()
    expect("items" in listing and "total" in listing, "list response shape")
    print(f"    total users: {listing['total']}")

    headline("6. POST /super-admin/users/invite")
    suffix = uuid.uuid4().hex[:8]
    invite_email = f"smoke_{suffix}@atom.local"
    r = session.post(
        f"{API}/super-admin/users/invite",
        data=json.dumps({"email": invite_email, "fullName": "Smoke Bot"}),
        headers=auth_headers(),
        timeout=10,
    )
    expect(r.status_code in (200, 201), f"invite -> {r.status_code} body={r.text[:200]}")
    invited = r.json()
    new_id = invited.get("id")
    expect(bool(new_id), "invited user has id")
    print(f"    invited id={new_id} email={invited.get('email')}")

    headline("7. PUT /super-admin/users/<id>/roles -> [employee]")
    r = session.put(
        f"{API}/super-admin/users/{new_id}/roles",
        data=json.dumps({"roles": ["employee"], "scope": "global", "reason": "smoke"}),
        headers=auth_headers(),
        timeout=10,
    )
    expect(r.status_code == 200, f"update roles -> {r.status_code} body={r.text[:200]}")
    roles_body = r.json()
    expect("employee" in roles_body.get("roles", []), "roles contains employee")
    expect(isinstance(roles_body.get("capabilities"), list), "response has capabilities list")

    headline("8. PUT /super-admin/users/<id>/capabilities add audit.view_all")
    r = session.put(
        f"{API}/super-admin/users/{new_id}/capabilities",
        data=json.dumps(
            {
                "capabilities_add": ["audit.view_all"],
                "capabilities_remove": [],
                "scope": "global",
                "reason": "smoke",
            }
        ),
        headers=auth_headers(),
        timeout=10,
    )
    expect(r.status_code == 200, f"update caps -> {r.status_code} body={r.text[:200]}")
    details = r.json()
    explicit_codes = [g["capability"] for g in details.get("explicit_capabilities", [])]
    expect("audit.view_all" in explicit_codes, "explicit grant added")
    expect("audit.view_all" in details.get("capabilities", []), "effective contains grant")

    headline("9. POST /super-admin/users/<id>/disable")
    r = session.post(
        f"{API}/super-admin/users/{new_id}/disable",
        data=json.dumps({"reason": "smoke"}),
        headers=auth_headers(),
        timeout=10,
    )
    expect(r.status_code == 200, f"disable -> {r.status_code}")
    expect(r.json().get("status") == "disabled", "status disabled")

    headline("10. POST /super-admin/users/<id>/enable")
    r = session.post(
        f"{API}/super-admin/users/{new_id}/enable",
        headers=auth_headers(),
        timeout=10,
    )
    expect(r.status_code == 200, f"enable -> {r.status_code}")
    expect(r.json().get("status") == "active", "status active")

    time.sleep(0.2)

    headline("11. GET /audit/events (last 10)")
    r = session.get(f"{API}/audit/events?page=1&page_size=10", timeout=10)
    expect(r.status_code == 200, f"/audit/events -> {r.status_code}")
    events = r.json()
    items = events.get("results") or events.get("items") or []
    print(f"    events page count={len(items)}")
    expect(len(items) > 0, "we produced some audit events")
    event_types = {item.get("event_type") for item in items}
    print(f"    types: {sorted(event_types)[:8]}...")
    expect(
        any("user" in t or "auth" in t or "invite" in t for t in event_types),
        "event_types include user/auth/invite",
    )

    headline("12. GET /audit/stats")
    r = session.get(f"{API}/audit/stats", timeout=10)
    expect(r.status_code == 200, f"/audit/stats -> {r.status_code}")
    stats = r.json()
    print(f"    stats: total={stats.get('events_total')} unique_actors={stats.get('unique_actors')}")
    expect(stats.get("events_total", 0) > 0, "events_total > 0")

    headline("13. GET /audit/events/export (CSV)")
    r = session.get(f"{API}/audit/events/export?limit=20", timeout=15)
    expect(r.status_code == 200, f"/audit/events/export -> {r.status_code}")
    ct = r.headers.get("Content-Type", "")
    expect("text/csv" in ct, f"Content-Type csv (got {ct})")
    cd = r.headers.get("Content-Disposition", "")
    expect("attachment" in cd, f"Content-Disposition attachment (got {cd})")
    text = r.text
    lines = text.splitlines()
    print(f"    csv lines: {len(lines)} first header: {lines[0][:80] if lines else ''}")
    expect(lines and lines[0].startswith("id,created_at,"), "csv header looks right")

    headline("14. POST /auth/logout")
    r = session.post(f"{API}/auth/logout", headers=auth_headers(), timeout=10)
    expect(r.status_code == 204, f"/auth/logout -> {r.status_code}")

    print("\n=== SMOKE PASS OK ===")


if __name__ == "__main__":
    main()

import argparse
import json

import requests

BASE = "http://127.0.0.1:8000/api/v1"


def parse_args():
    parser = argparse.ArgumentParser(description="Smoke test for chat members management API")
    parser.add_argument("--username", default="super_admin_test")
    parser.add_argument("--password", default="AtomTest123!")
    parser.add_argument("--chat-id", type=int, required=True)
    parser.add_argument("--member-user-id", type=int, required=True)
    parser.add_argument("--promote-owner", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = requests.Session()
    csrf = session.get(f"{BASE}/auth/csrf", timeout=10)
    assert csrf.status_code == 200, csrf.text

    def headers() -> dict[str, str]:
        return {
            "Referer": "http://127.0.0.1:8000/",
            "X-CSRFToken": session.cookies.get("csrftoken", ""),
            "Content-Type": "application/json",
        }

    login = session.post(
        f"{BASE}/auth/login",
        data=json.dumps({"username": args.username, "password": args.password}),
        headers=headers(),
        timeout=10,
    )
    assert login.status_code == 200, login.text

    members_url = f"{BASE}/chats/{args.chat_id}/members"
    member_url = f"{members_url}/{args.member_user_id}"

    list_before = session.get(members_url, timeout=10)
    assert list_before.status_code == 200, list_before.text
    print("members_before:", len((list_before.json() or {}).get("results") or []))

    add_payload = {"user_id": args.member_user_id, "role": "member"}
    add_resp = session.post(
        members_url,
        data=json.dumps(add_payload),
        headers=headers(),
        timeout=10,
    )
    assert add_resp.status_code in (200, 201), (add_resp.status_code, add_resp.text)
    print("add_or_upsert_ok:", add_resp.status_code)

    patch_role = "owner" if args.promote_owner else "member"
    patch_resp = session.patch(
        member_url,
        data=json.dumps({"role": patch_role}),
        headers=headers(),
        timeout=10,
    )
    assert patch_resp.status_code == 200, (patch_resp.status_code, patch_resp.text)
    print("patch_ok role:", (patch_resp.json() or {}).get("role"))

    delete_resp = session.delete(member_url, headers=headers(), timeout=10)
    assert delete_resp.status_code == 204, (delete_resp.status_code, delete_resp.text)
    print("delete_ok")

    list_after = session.get(members_url, timeout=10)
    assert list_after.status_code == 200, list_after.text
    print("members_after:", len((list_after.json() or {}).get("results") or []))

    logout = session.post(f"{BASE}/auth/logout", headers=headers(), timeout=10)
    assert logout.status_code == 204, logout.text
    print("CHAT MEMBERS SMOKE OK")


if __name__ == "__main__":
    main()

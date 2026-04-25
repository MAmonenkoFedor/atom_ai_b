import argparse
import json

import requests

BASE = "http://127.0.0.1:8000/api/v1"


def parse_args():
    parser = argparse.ArgumentParser(description="Smoke test for /api/v1/ai/chat/completions")
    parser.add_argument("--username", default="super_admin_test")
    parser.add_argument("--password", default="AtomTest123!")
    parser.add_argument("--thread-id", type=int, required=True)
    parser.add_argument("--message", default="Дай короткий статус по проекту.")
    parser.add_argument("--model", default="")
    parser.add_argument("--context-type", default="")
    parser.add_argument("--context-id", default="")
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

    payload = {
        "thread_id": args.thread_id,
        "message": args.message,
    }
    if args.model:
        payload["model"] = args.model
    if args.context_type:
        payload["context_type"] = args.context_type
    if args.context_id:
        payload["context_id"] = args.context_id

    resp = session.post(
        f"{BASE}/ai/chat/completions",
        data=json.dumps(payload),
        headers=headers(),
        timeout=60,
    )
    assert resp.status_code == 200, (resp.status_code, resp.text)
    body = resp.json()
    print("thread_id:", body.get("thread_id"))
    print("message_id:", body.get("message_id"))
    print("provider:", body.get("provider"))
    print("model:", body.get("model"))
    usage = body.get("usage") or {}
    print(
        "usage:",
        {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "cost_estimate": usage.get("cost_estimate"),
        },
    )
    print("output:", (body.get("output_text") or "")[:300])

    logout = session.post(f"{BASE}/auth/logout", headers=headers(), timeout=10)
    assert logout.status_code == 204, logout.text
    print("OPENROUTER CHAT SMOKE OK")


if __name__ == "__main__":
    main()

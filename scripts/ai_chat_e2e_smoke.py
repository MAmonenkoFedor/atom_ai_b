import argparse
import json
import uuid

import requests

BASE = "http://127.0.0.1:8000/api/v1"


def parse_args():
    parser = argparse.ArgumentParser(description="E2E smoke for shared AI chat and audit usage.")
    parser.add_argument("--username", default="super_admin_test")
    parser.add_argument("--password", default="AtomTest123!")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--member-user-id", type=int, required=True)
    parser.add_argument("--context-type", default="")
    parser.add_argument("--context-id", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--cleanup-chat", action="store_true")
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

    title = f"AI E2E SMOKE {uuid.uuid4().hex[:6]}"
    chat_create = session.post(
        f"{BASE}/chats",
        data=json.dumps({"project": args.project_id, "title": title, "status": "open"}),
        headers=headers(),
        timeout=10,
    )
    assert chat_create.status_code == 201, (chat_create.status_code, chat_create.text)
    chat_id = chat_create.json()["id"]
    print("chat_created:", chat_id, title)

    try:
        member_add = session.post(
            f"{BASE}/chats/{chat_id}/members",
            data=json.dumps({"user_id": args.member_user_id, "role": "member"}),
            headers=headers(),
            timeout=10,
        )
        assert member_add.status_code in (200, 201), (member_add.status_code, member_add.text)
        print("member_added:", args.member_user_id)

        ai_payload = {
            "thread_id": chat_id,
            "message": "Сделай короткий статус по проекту и следующие шаги.",
        }
        if args.model:
            ai_payload["model"] = args.model
        if args.context_type:
            ai_payload["context_type"] = args.context_type
        if args.context_id:
            ai_payload["context_id"] = args.context_id

        ai_resp = session.post(
            f"{BASE}/ai/chat/completions",
            data=json.dumps(ai_payload),
            headers=headers(),
            timeout=60,
        )
        assert ai_resp.status_code == 200, (ai_resp.status_code, ai_resp.text)
        ai_body = ai_resp.json()
        print("ai_message_id:", ai_body.get("message_id"))
        print("provider/model:", ai_body.get("provider"), ai_body.get("model"))
        usage = ai_body.get("usage") or {}
        print(
            "usage:",
            {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cost_estimate": usage.get("cost_estimate"),
            },
        )

        audit_resp = session.get(
            f"{BASE}/audit/ai-usage-stats",
            params={"chat_id": str(chat_id)},
            timeout=15,
        )
        assert audit_resp.status_code == 200, (audit_resp.status_code, audit_resp.text)
        audit_body = audit_resp.json()
        totals = audit_body.get("totals") or {}
        assert int(totals.get("requests") or 0) >= 1, audit_body
        print("audit_requests:", totals.get("requests"))
        print("audit_total_tokens:", totals.get("total_tokens"))

        print("AI CHAT E2E SMOKE OK")
    finally:
        # Best-effort cleanup of added member.
        session.delete(f"{BASE}/chats/{chat_id}/members/{args.member_user_id}", headers=headers(), timeout=10)
        if args.cleanup_chat:
            close_resp = session.patch(
                f"{BASE}/chats/{chat_id}",
                data=json.dumps({"status": "closed"}),
                headers=headers(),
                timeout=10,
            )
            if close_resp.status_code in (200, 204):
                print("chat_cleanup: closed")
            else:
                print(
                    "chat_cleanup: skipped (endpoint may not support PATCH yet), status:",
                    close_resp.status_code,
                )

    logout = session.post(f"{BASE}/auth/logout", headers=headers(), timeout=10)
    assert logout.status_code == 204, logout.text


if __name__ == "__main__":
    main()

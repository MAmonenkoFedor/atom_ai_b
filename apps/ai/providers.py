import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings


@dataclass
class ProviderResult:
    provider: str
    model: str
    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_estimate: float


class BaseAIProvider:
    provider_code = "base"

    def chat_completions(
        self,
        *,
        messages: list[dict],
        model: str,
        max_tokens: int,
    ) -> ProviderResult:
        raise NotImplementedError

    @staticmethod
    def _post_json(url: str, payload: dict, headers: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)
        timeout_seconds = max(3, int(settings.LLM_GATEWAY_TIMEOUT_MS) // 1000)
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Provider HTTP {exc.code}: {raw[:600]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Provider network error: {exc.reason}") from exc

    @staticmethod
    def _get_json(url: str, headers: dict) -> dict:
        req = urllib.request.Request(url=url, method="GET")
        for key, value in headers.items():
            req.add_header(key, value)
        timeout_seconds = max(3, int(settings.LLM_GATEWAY_TIMEOUT_MS) // 1000)
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Provider HTTP {exc.code}: {raw[:600]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Provider network error: {exc.reason}") from exc


class OpenRouterProvider(BaseAIProvider):
    provider_code = "openrouter"

    def chat_completions(
        self,
        *,
        messages: list[dict],
        model: str,
        max_tokens: int,
    ) -> ProviderResult:
        api_key = (settings.OPENROUTER_API_KEY or "").strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        base_url = (settings.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1").rstrip("/")
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": int(max_tokens),
            "temperature": 0.2,
        }
        data = self._post_json(
            url=f"{base_url}/chat/completions",
            payload=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        choices = data.get("choices") or []
        content = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
        cost_estimate = float(usage.get("cost") or 0.0)
        resolved_model = str(data.get("model") or model)
        return ProviderResult(
            provider=self.provider_code,
            model=resolved_model,
            text=content.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_estimate=cost_estimate,
        )


class HiggsfieldProvider(BaseAIProvider):
    """Higgsfield queue API: POST model path → poll /requests/{id}/status until terminal state."""

    provider_code = "higgsfield"

    def _auth_header(self) -> str:
        key = (settings.HIGGSFIELD_API_KEY or "").strip()
        secret = (settings.HIGGSFIELD_API_SECRET or "").strip()
        if not key:
            raise RuntimeError("HIGGSFIELD_API_KEY is not configured")
        # Docs: Authorization: Key {api_key}:{api_secret}. Some vendors issue a single token — use it twice.
        if not secret:
            secret = key
        return f"Key {key}:{secret}"

    def generate_image(
        self,
        *,
        prompt: str,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
    ) -> ProviderResult:
        base = (settings.HIGGSFIELD_BASE_URL or "https://platform.higgsfield.ai").rstrip("/")
        model_path = (settings.HIGGSFIELD_MODEL_PATH or "").strip().strip("/")
        if not model_path:
            raise RuntimeError("HIGGSFIELD_MODEL_PATH is not configured")
        ar = (aspect_ratio or settings.HIGGSFIELD_DEFAULT_ASPECT_RATIO or "16:9").strip()
        res = (resolution or settings.HIGGSFIELD_DEFAULT_RESOLUTION or "720p").strip()
        submit_url = f"{base}/{model_path}"
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }
        body = {"prompt": prompt, "aspect_ratio": ar, "resolution": res}
        queued = self._post_json(submit_url, body, headers)
        request_id = str(queued.get("request_id") or "").strip()
        if not request_id:
            raise RuntimeError(f"Higgsfield submit: missing request_id in response: {queued!r:.500}")
        status_url = (queued.get("status_url") or "").strip() or f"{base}/requests/{request_id}/status"

        interval = max(0.5, float(getattr(settings, "HIGGSFIELD_POLL_INTERVAL_SEC", 2.0) or 2.0))
        timeout = max(5, int(getattr(settings, "HIGGSFIELD_POLL_TIMEOUT_SEC", 180) or 180))
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            st = self._get_json(status_url, headers)
            st_name = str(st.get("status") or "").strip().lower()
            if st_name == "completed":
                lines: list[str] = []
                for img in st.get("images") or []:
                    if isinstance(img, dict):
                        u = (img.get("url") or "").strip()
                        if u:
                            lines.append(f"![image]({u})")
                vid = st.get("video")
                if isinstance(vid, dict):
                    vu = (vid.get("url") or "").strip()
                    if vu:
                        lines.append(f"[Видео]({vu})")
                text = "\n\n".join(lines) if lines else "(completed, no media URLs in response)"
                return ProviderResult(
                    provider=self.provider_code,
                    model=model_path,
                    text=text,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    cost_estimate=0.0,
                )
            if st_name in ("failed", "nsfw"):
                raise RuntimeError(f"Higgsfield generation {st_name}: {st!r:.800}")
            if st_name in ("queued", "in_progress", ""):
                time.sleep(interval)
                continue
            raise RuntimeError(f"Higgsfield unknown status {st_name!r}: {st!r:.800}")

        raise RuntimeError(f"Higgsfield poll timeout after {timeout}s (request_id={request_id})")

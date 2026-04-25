import json
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

    def chat_completions(self, *, messages: list[dict], model: str, max_tokens: int) -> ProviderResult:
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


class OpenRouterProvider(BaseAIProvider):
    provider_code = "openrouter"

    def chat_completions(self, *, messages: list[dict], model: str, max_tokens: int) -> ProviderResult:
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

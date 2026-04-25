from dataclasses import dataclass
import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings


@dataclass
class AdapterResult:
    text: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class BaseAdapter:
    provider_code = "base"

    def generate(self, prompt: str, model_code: str, provider=None) -> AdapterResult:
        # Deterministic switch to test fallback/retry flow without external APIs.
        if f"force_fail:{self.provider_code}" in prompt:
            raise RuntimeError(f"Forced failure for provider {self.provider_code}")

        if provider is not None and provider.mock_override is not None:
            if provider.mock_override:
                return self._mock_response(prompt=prompt, model_code=model_code)
            return self._real_generate(prompt=prompt, model_code=model_code, provider=provider)

        if settings.LLM_GATEWAY_MOCK_MODE:
            return self._mock_response(prompt=prompt, model_code=model_code)
        return self._real_generate(prompt=prompt, model_code=model_code, provider=provider)

    def _real_generate(self, prompt: str, model_code: str, provider=None) -> AdapterResult:
        raise NotImplementedError

    @staticmethod
    def _mock_response(prompt: str, model_code: str) -> AdapterResult:
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(8, min(256, prompt_tokens // 2))
        text = f"Mock response for prompt: {prompt[:200]}"
        return AdapterResult(text=text, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    @staticmethod
    def _request_json(url: str, payload: dict, headers: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)

        timeout_seconds = max(1, int(settings.LLM_GATEWAY_TIMEOUT_MS) // 1000)
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {raw[:800]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc


class OpenAIAdapter(BaseAdapter):
    provider_code = "openai"

    def _real_generate(self, prompt: str, model_code: str, provider=None) -> AdapterResult:
        provider_cfg = provider.config if provider and isinstance(provider.config, dict) else {}
        api_key = (provider_cfg.get("api_key") or "").strip() or settings.OPENAI_API_KEY
        base_url = (provider_cfg.get("base_url") or "").strip() or settings.OPENAI_BASE_URL
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        base_url = base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model_code,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        data = self._request_json(url=url, payload=payload, headers=headers)
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return AdapterResult(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", max(1, len(prompt.split())))),
            completion_tokens=int(usage.get("completion_tokens", max(8, len(text.split()) // 2))),
        )


class ClaudeAdapter(BaseAdapter):
    provider_code = "claude"

    def _real_generate(self, prompt: str, model_code: str, provider=None) -> AdapterResult:
        provider_cfg = provider.config if provider and isinstance(provider.config, dict) else {}
        api_key = (provider_cfg.get("api_key") or "").strip() or settings.ANTHROPIC_API_KEY
        base_url = (provider_cfg.get("base_url") or "").strip() or settings.ANTHROPIC_BASE_URL
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        base_url = base_url.rstrip("/")
        url = f"{base_url}/messages"
        payload = {
            "model": model_code,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        data = self._request_json(url=url, payload=payload, headers=headers)
        content = data.get("content", [])
        text_parts = [part.get("text", "") for part in content if part.get("type") == "text"]
        text = "\n".join([p for p in text_parts if p]).strip() or "(empty response)"
        usage = data.get("usage", {})
        return AdapterResult(
            text=text,
            prompt_tokens=int(usage.get("input_tokens", max(1, len(prompt.split())))),
            completion_tokens=int(usage.get("output_tokens", max(8, len(text.split()) // 2))),
        )


class GeminiAdapter(BaseAdapter):
    provider_code = "gemini"

    def _real_generate(self, prompt: str, model_code: str, provider=None) -> AdapterResult:
        provider_cfg = provider.config if provider and isinstance(provider.config, dict) else {}
        api_key = (provider_cfg.get("api_key") or "").strip() or settings.GEMINI_API_KEY
        base_url = (provider_cfg.get("base_url") or "").strip() or settings.GEMINI_BASE_URL
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        base_url = base_url.rstrip("/")
        query = urllib.parse.urlencode({"key": api_key})
        url = f"{base_url}/models/{model_code}:generateContent?{query}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data = self._request_json(url=url, payload=payload, headers={})
        candidates = data.get("candidates", [])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "\n".join([part.get("text", "") for part in parts if part.get("text")]).strip()
        if not text:
            text = "(empty response)"
        usage = data.get("usageMetadata", {})
        return AdapterResult(
            text=text,
            prompt_tokens=int(usage.get("promptTokenCount", max(1, len(prompt.split())))),
            completion_tokens=int(usage.get("candidatesTokenCount", max(8, len(text.split()) // 2))),
        )

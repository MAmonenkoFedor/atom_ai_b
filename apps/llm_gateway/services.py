import time
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.llm_gateway.adapters import ClaudeAdapter, GeminiAdapter, OpenAIAdapter
from apps.llm_gateway.models import LlmModel, LlmModelProfile, LlmProvider, LlmRequestLog


@dataclass
class RouteResult:
    profile: LlmModelProfile | None
    model: LlmModel
    provider: LlmProvider


class LlmGatewayService:
    PROFILE_SEEDS = [
        ("chat_fast", "Fast chat responses", ("openai", "gpt-4.1-mini"), ("gemini", "gemini-2.0-flash")),
        ("chat_balanced", "Balanced quality and speed", ("claude", "claude-3-5-haiku"), ("openai", "gpt-4.1-mini")),
        ("chat_deep", "Deeper reasoning", ("openai", "gpt-4.1"), ("claude", "claude-3-7-sonnet")),
        ("summary_fast", "Fast summary generation", ("gemini", "gemini-2.0-flash"), ("openai", "gpt-4.1-mini")),
        ("summary_batch", "Batch summary profile", ("claude", "claude-3-5-haiku"), ("gemini", "gemini-2.0-flash")),
    ]

    ADAPTERS = {
        "openai": OpenAIAdapter(),
        "claude": ClaudeAdapter(),
        "gemini": GeminiAdapter(),
    }

    @transaction.atomic
    def ensure_seed_data(self) -> None:
        providers = {
            "openai": self._upsert_provider("openai", "OpenAI", 10),
            "claude": self._upsert_provider("claude", "Anthropic Claude", 20),
            "gemini": self._upsert_provider("gemini", "Google Gemini", 30),
        }

        models = {
            ("openai", "gpt-4.1-mini"): self._upsert_model(providers["openai"], "gpt-4.1-mini", 128000),
            ("openai", "gpt-4.1"): self._upsert_model(providers["openai"], "gpt-4.1", 128000),
            ("claude", "claude-3-5-haiku"): self._upsert_model(providers["claude"], "claude-3-5-haiku", 200000),
            ("claude", "claude-3-7-sonnet"): self._upsert_model(providers["claude"], "claude-3-7-sonnet", 200000),
            ("gemini", "gemini-2.0-flash"): self._upsert_model(providers["gemini"], "gemini-2.0-flash", 1000000),
        }

        for code, description, primary_ref, fallback_ref in self.PROFILE_SEEDS:
            primary_model = models[primary_ref]
            fallback_model = models[fallback_ref]
            profile, _ = LlmModelProfile.objects.get_or_create(
                code=code,
                defaults={
                    "description": description,
                    "is_active": True,
                    "primary_model": primary_model,
                    "fallback_model": fallback_model,
                },
            )
            changed = False
            if profile.primary_model_id != primary_model.id:
                profile.primary_model = primary_model
                changed = True
            if profile.fallback_model_id != fallback_model.id:
                profile.fallback_model = fallback_model
                changed = True
            if not profile.description:
                profile.description = description
                changed = True
            if changed:
                profile.save(
                    update_fields=["primary_model", "fallback_model", "description"]
                )

    def route(
        self,
        profile_code: str | None,
        requested_provider_code: str | None = None,
        requested_model_code: str | None = None,
    ) -> RouteResult:
        self.ensure_seed_data()
        profile = None

        if requested_provider_code and requested_model_code:
            provider = LlmProvider.objects.get(code=requested_provider_code, is_active=True)
            model = LlmModel.objects.get(
                provider=provider,
                code=requested_model_code,
                is_active=True,
            )
            return RouteResult(profile=None, model=model, provider=provider)

        profile_key = profile_code or "chat_balanced"
        profile = LlmModelProfile.objects.select_related(
            "primary_model__provider", "fallback_model__provider"
        ).get(code=profile_key, is_active=True)

        chosen_model = profile.primary_model or profile.fallback_model
        if chosen_model is None:
            raise ValueError(f"Profile {profile.code} has no model configured")

        return RouteResult(profile=profile, model=chosen_model, provider=chosen_model.provider)

    def build_route_candidates(
        self,
        profile_code: str | None,
        requested_provider_code: str | None = None,
        requested_model_code: str | None = None,
    ) -> list[RouteResult]:
        primary = self.route(
            profile_code=profile_code,
            requested_provider_code=requested_provider_code,
            requested_model_code=requested_model_code,
        )

        # Explicit provider/model request should not fallback silently.
        if requested_provider_code and requested_model_code:
            return [primary]

        if not settings.LLM_GATEWAY_ENABLE_FALLBACK:
            return [primary]

        if primary.profile is None or primary.profile.fallback_model is None:
            return [primary]

        fallback_model = primary.profile.fallback_model
        if fallback_model.id == primary.model.id:
            return [primary]

        fallback = RouteResult(
            profile=primary.profile,
            model=fallback_model,
            provider=fallback_model.provider,
        )
        return [primary, fallback]

    def execute(
        self,
        *,
        ai_run,
        prompt: str,
        profile_code: str | None = None,
        requested_provider_code: str | None = None,
        requested_model_code: str | None = None,
    ) -> dict:
        routes = self.build_route_candidates(
            profile_code=profile_code,
            requested_provider_code=requested_provider_code,
            requested_model_code=requested_model_code,
        )
        max_retries = max(1, int(settings.LLM_GATEWAY_MAX_RETRIES))
        timeout_ms = int(settings.LLM_GATEWAY_TIMEOUT_MS)
        last_error = "LLM adapter execution failed"

        for route in routes:
            adapter = self.ADAPTERS.get(route.provider.code)
            if adapter is None:
                last_error = f"No adapter for provider '{route.provider.code}'"
                LlmRequestLog.objects.create(
                    ai_run=ai_run,
                    profile=route.profile,
                    provider=route.provider,
                    model=route.model,
                    status=LlmRequestLog.STATUS_ERROR,
                    latency_ms=0,
                    error_message=last_error,
                )
                continue

            for attempt in range(1, max_retries + 1):
                started = time.perf_counter()
                status = LlmRequestLog.STATUS_SUCCESS
                error_message = ""
                result = None
                try:
                    result = adapter.generate(prompt=prompt, model_code=route.model.code)
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    if elapsed_ms > timeout_ms:
                        raise TimeoutError(
                            f"Gateway timeout exceeded ({elapsed_ms}ms > {timeout_ms}ms)"
                        )
                except Exception as exc:
                    status = LlmRequestLog.STATUS_ERROR
                    error_message = str(exc)
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    last_error = error_message

                LlmRequestLog.objects.create(
                    ai_run=ai_run,
                    profile=route.profile,
                    provider=route.provider,
                    model=route.model,
                    status=status,
                    prompt_tokens=result.prompt_tokens if result else 0,
                    completion_tokens=result.completion_tokens if result else 0,
                    total_tokens=result.total_tokens if result else 0,
                    latency_ms=elapsed_ms,
                    error_message=error_message,
                    response_excerpt=result.text[:500] if result else "",
                )

                if status == LlmRequestLog.STATUS_SUCCESS and result is not None:
                    return {
                        "provider_code": route.provider.code,
                        "model_code": route.model.code,
                        "profile_code": route.profile.code if route.profile else None,
                        "text": result.text,
                        "usage": {
                            "prompt_tokens": result.prompt_tokens,
                            "completion_tokens": result.completion_tokens,
                            "total_tokens": result.total_tokens,
                        },
                        "latency_ms": elapsed_ms,
                        "attempt": attempt,
                    }

        raise RuntimeError(last_error)

    @staticmethod
    def _upsert_provider(code: str, name: str, priority: int) -> LlmProvider:
        provider, _ = LlmProvider.objects.get_or_create(
            code=code,
            defaults={"name": name, "priority": priority, "is_active": True},
        )
        updates = []
        if provider.name != name:
            provider.name = name
            updates.append("name")
        if provider.priority != priority:
            provider.priority = priority
            updates.append("priority")
        if updates:
            provider.save(update_fields=updates)
        return provider

    @staticmethod
    def _upsert_model(provider: LlmProvider, code: str, context_window: int) -> LlmModel:
        model, _ = LlmModel.objects.get_or_create(
            provider=provider,
            code=code,
            defaults={
                "display_name": code,
                "is_active": True,
                "context_window": context_window,
            },
        )
        updates = []
        if model.context_window != context_window:
            model.context_window = context_window
            updates.append("context_window")
        if not model.display_name:
            model.display_name = code
            updates.append("display_name")
        if updates:
            model.save(update_fields=updates)
        return model

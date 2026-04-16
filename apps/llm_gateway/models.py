from django.db import models


class LlmProvider(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=100)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("priority", "code")

    def __str__(self) -> str:
        return self.code


class LlmModel(models.Model):
    provider = models.ForeignKey(
        LlmProvider,
        on_delete=models.CASCADE,
        related_name="models",
    )
    code = models.CharField(max_length=128)
    display_name = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True)
    context_window = models.IntegerField(default=0)
    input_cost_per_1k = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    output_cost_per_1k = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "code"),
                name="uniq_llm_model_per_provider",
            )
        ]
        ordering = ("provider_id", "code")

    def __str__(self) -> str:
        return f"{self.provider.code}:{self.code}"


class LlmModelProfile(models.Model):
    code = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    primary_model = models.ForeignKey(
        LlmModel,
        on_delete=models.SET_NULL,
        related_name="primary_for_profiles",
        null=True,
        blank=True,
    )
    fallback_model = models.ForeignKey(
        LlmModel,
        on_delete=models.SET_NULL,
        related_name="fallback_for_profiles",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code


class LlmRequestLog(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Success"),
        (STATUS_ERROR, "Error"),
    )

    ai_run = models.ForeignKey(
        "ai.AiRun",
        on_delete=models.SET_NULL,
        related_name="gateway_logs",
        null=True,
        blank=True,
    )
    profile = models.ForeignKey(
        LlmModelProfile,
        on_delete=models.SET_NULL,
        related_name="request_logs",
        null=True,
        blank=True,
    )
    provider = models.ForeignKey(
        LlmProvider,
        on_delete=models.SET_NULL,
        related_name="request_logs",
        null=True,
        blank=True,
    )
    model = models.ForeignKey(
        LlmModel,
        on_delete=models.SET_NULL,
        related_name="request_logs",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    response_excerpt = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.id}:{self.status}"

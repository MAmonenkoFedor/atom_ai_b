from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["127.0.0.1", "localhost"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-dev-secret")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])
CORS_EXPOSE_HEADERS = ["X-Request-Id"]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-request-id",
    "x-trace-id",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.identity",
    "apps.organizations",
    "apps.orgstructure",
    "apps.workspaces",
    "apps.projects",
    "apps.chats",
    "apps.ai",
    "apps.llm_gateway",
    "apps.audit",
    "apps.storage",
    "apps.access",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgresql://atom_ai:atom_ai@localhost:5433/atom_ai",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.core.api.exceptions.unified_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ATOM AI Backend API",
    "DESCRIPTION": "API contract for ATOM AI Workspace",
    "VERSION": "1.0.0",
    "ENUM_NAME_OVERRIDES": {
        "ProjectStatusEnum": [
            ("active", "Active"),
            ("on_hold", "On Hold"),
            ("completed", "Completed"),
            ("archived", "Archived"),
        ],
        "CompanyUserStatusEnum": ["active", "invited", "blocked"],
        "InviteStatusEnum": ["pending", "accepted", "expired", "revoked"],
        "TenantStatusEnum": ["active", "trial", "suspended"],
        "RequestStatusEnum": ["success", "failed"],
        "TaskStatusEnum": ["todo", "in_progress", "done"],
        "CompanyUserRoleEnum": ["employee", "manager", "company_admin"],
        "PlatformRoleEnum": ["platform_admin", "support", "security"],
        "ProjectMemberRoleEnum": [
            ("owner", "Owner"),
            ("editor", "Editor"),
            ("viewer", "Viewer"),
        ],
    },
}

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env(
    "CELERY_RESULT_BACKEND",
    default="redis://localhost:6379/2",
)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

LLM_GATEWAY_TIMEOUT_MS = env.int("LLM_GATEWAY_TIMEOUT_MS", default=30000)
LLM_GATEWAY_MAX_RETRIES = env.int("LLM_GATEWAY_MAX_RETRIES", default=1)
LLM_GATEWAY_ENABLE_FALLBACK = env.bool("LLM_GATEWAY_ENABLE_FALLBACK", default=True)
LLM_GATEWAY_MOCK_MODE = env.bool("LLM_GATEWAY_MOCK_MODE", default=True)
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", default="https://api.openai.com/v1")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
ANTHROPIC_BASE_URL = env("ANTHROPIC_BASE_URL", default="https://api.anthropic.com/v1")
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_BASE_URL = env(
    "GEMINI_BASE_URL",
    default="https://generativelanguage.googleapis.com/v1beta",
)
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", default="")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
DEFAULT_AI_MODEL = env("DEFAULT_AI_MODEL", default="openai/gpt-4o-mini")
AI_CHAT_MAX_TOKENS = env.int("AI_CHAT_MAX_TOKENS", default=800)
AI_CHAT_HISTORY_LIMIT = env.int("AI_CHAT_HISTORY_LIMIT", default=20)
AI_CHAT_RATE_LIMIT_USER_PER_MINUTE = env.int("AI_CHAT_RATE_LIMIT_USER_PER_MINUTE", default=20)
AI_CHAT_RATE_LIMIT_COMPANY_PER_MINUTE = env.int("AI_CHAT_RATE_LIMIT_COMPANY_PER_MINUTE", default=120)
AI_SYSTEM_PROMPT = env(
    "AI_SYSTEM_PROMPT",
    default=(
        "You are the ATOM AI assistant. Give concise, actionable and safe responses. "
        "Use only provided context and chat history."
    ),
)

# Curated whitelist of OpenRouter model ids that users can pick from in the chat.
# Keep this intentionally small — super-admin can extend it as the platform matures.
# Any model id passed by the frontend is validated against this list.
AI_CHAT_ALLOWED_MODELS = [
    {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o mini",
        "provider": "OpenAI",
        "specialty": "Быстрая и универсальная",
        "description": (
            "Бюджетная модель для ежедневных задач: короткие ответы, "
            "резюме, классификация, быстрые черновики."
        ),
        "is_default": True,
        "context_tokens": 128000,
    },
    {
        "id": "openai/gpt-4o",
        "name": "GPT-4o",
        "provider": "OpenAI",
        "specialty": "Умный универсал",
        "description": "Сильная общая модель: аналитика, код, длинные инструкции.",
        "is_default": False,
        "context_tokens": 128000,
    },
    {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "provider": "Anthropic",
        "specialty": "Длинный контекст",
        "description": "Хорош на больших документах, договорах и аккуратной аналитике.",
        "is_default": False,
        "context_tokens": 200000,
    },
    {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Claude 3.5 Haiku",
        "provider": "Anthropic",
        "specialty": "Лёгкая и быстрая",
        "description": "Дешёвая модель Anthropic для простых ответов и классификации.",
        "is_default": False,
        "context_tokens": 200000,
    },
    {
        "id": "google/gemini-2.0-flash-001",
        "name": "Gemini 2.0 Flash",
        "provider": "Google",
        "specialty": "Мультимодальная",
        "description": "Быстрая Google-модель с поддержкой картинок и длинного контекста.",
        "is_default": False,
        "context_tokens": 1000000,
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B",
        "provider": "Meta",
        "specialty": "Открытая модель",
        "description": "Сильная open-source альтернатива, подходит для внутренних задач.",
        "is_default": False,
        "context_tokens": 128000,
    },
    {
        "id": "mistralai/mistral-large-latest",
        "name": "Mistral Large",
        "provider": "Mistral",
        "specialty": "Европейский провайдер",
        "description": "Сильная модель Mistral: хороший русский/французский, рассуждения.",
        "is_default": False,
        "context_tokens": 128000,
    },
    {
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek Chat",
        "provider": "DeepSeek",
        "specialty": "Бюджетный reasoning",
        "description": "Дешёвая модель с хорошим качеством для кода и логических задач.",
        "is_default": False,
        "context_tokens": 64000,
    },
]

# Optional Fernet key (urlsafe base64). Empty → derive from SECRET_KEY (rotate = re-enter provider secrets).
STORAGE_CREDENTIALS_FERNET_KEY = env("STORAGE_CREDENTIALS_FERNET_KEY", default="")

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

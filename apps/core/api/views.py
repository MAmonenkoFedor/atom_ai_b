from django.db import connection
from redis import Redis
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthLiveView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class HealthReadyView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        db_ok = self._check_db()
        redis_ok = self._check_redis()
        status = "ok" if db_ok and redis_ok else "degraded"
        return Response(
            {
                "status": status,
                "checks": {
                    "database": "ok" if db_ok else "error",
                    "redis": "ok" if redis_ok else "error",
                },
            },
            status=200 if status == "ok" else 503,
        )

    @staticmethod
    def _check_db() -> bool:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
            return bool(row and row[0] == 1)
        except Exception:
            return False

    @staticmethod
    def _check_redis() -> bool:
        try:
            from django.conf import settings

            client = Redis.from_url(settings.REDIS_URL)
            pong = client.ping()
            return bool(pong)
        except Exception:
            return False

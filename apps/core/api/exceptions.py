from rest_framework import status
from rest_framework.views import exception_handler


DRF_DETAIL_PATH_PREFIXES = (
    "/api/auth/",
    "/api/v1/auth/",
    "/api/projects",
    "/api/v1/projects",
    "/api/company/admin/",
    "/api/v1/company/admin/",
    "/api/admin/company/",
    "/api/v1/admin/company/",
    "/api/admin/platform/",
    "/api/v1/admin/platform/",
    "/api/platform/admin/",
    "/api/v1/platform/admin/",
    "/api/admin/actions/",
    "/api/v1/admin/actions/",
    "/api/admin/action-center/",
    "/api/v1/admin/action-center/",
    "/api/tasks",
    "/api/v1/tasks",
    "/api/buildings",
    "/api/v1/buildings",
    "/api/workspace/",
    "/api/v1/workspace/",
    "/api/employees/",
    "/api/v1/employees/",
)


def _extract_message(detail):
    if isinstance(detail, dict):
        if "detail" in detail:
            return str(detail["detail"])
        if detail:
            first_value = next(iter(detail.values()))
            if isinstance(first_value, list) and first_value:
                return str(first_value[0])
            return str(first_value)
        return "Request failed"
    if isinstance(detail, list):
        return str(detail[0]) if detail else "Request failed"
    return str(detail)


def _is_drf_detail_contract_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in DRF_DETAIL_PATH_PREFIXES)


def unified_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return response

    request = context.get("request")
    request_path = request.path if request else ""
    if _is_drf_detail_contract_path(request_path):
        response.data = {"detail": _extract_message(response.data)}
        return response

    error_type = "validation_error" if response.status_code == 400 else "api_error"
    detail = response.data
    message = _extract_message(detail)

    response.data = {
        "error": {
            "type": error_type,
            "code": response.status_code,
            "message": message,
            "details": detail,
        }
    }
    return response

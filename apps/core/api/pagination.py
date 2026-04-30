from __future__ import annotations


def offset_paginate(queryset, request):
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get("page_size", 25))
    except (TypeError, ValueError):
        page_size = 25
    page_size = max(1, min(page_size, 100))

    total = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = list(queryset[start:end])
    return items, page, page_size, total
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "num_pages": self.page.paginator.num_pages,
                "results": data,
            }
        )

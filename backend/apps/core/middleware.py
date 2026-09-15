"""Dev-only request timing: total time vs time spent in SQL, so proxy stalls and DB stalls are told apart."""

import logging
import time

from django.db import connection
from django.utils.deprecation import MiddlewareMixin

log = logging.getLogger("attool.timing")


class RequestTimingMiddleware(MiddlewareMixin):
    """Works in both the sync and the async request path (the scrim event stream is async)."""

    def process_request(self, request):
        request._timing_start = time.perf_counter()
        request._timing_queries = len(connection.queries)

    def process_response(self, request, response):
        start = getattr(request, "_timing_start", None)
        if start is None:
            return response
        total_ms = (time.perf_counter() - start) * 1000
        queries = connection.queries[getattr(request, "_timing_queries", 0) :]
        db_ms = sum(float(q.get("time", 0)) for q in queries) * 1000
        log.info(
            "%s %s %s total=%.0fms db=%.0fms queries=%d",
            request.method,
            request.get_full_path(),
            response.status_code,
            total_ms,
            db_ms,
            len(queries),
        )
        return response

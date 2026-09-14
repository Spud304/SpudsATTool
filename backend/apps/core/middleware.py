"""Dev-only request timing: total time vs time spent in SQL, so proxy stalls and DB stalls are told apart."""

import logging
import time

from django.db import connection

log = logging.getLogger("attool.timing")


class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        before = len(connection.queries)
        response = self.get_response(request)
        total_ms = (time.perf_counter() - start) * 1000
        queries = connection.queries[before:]
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

"""Route matching helper (pinned by contract).

BaseHTTPMiddleware runs before FastAPI routing, so the matched route is not
yet in the request scope. ``match_route`` finds the route the app itself would
match, by iterating ``app.routes`` and using each route's own ``matches()``.
"""

from starlette.routing import Match


def match_route(app, scope) -> tuple[str, str] | None:
    """Return ``(HTTP_METHOD, path_template)`` for the route that matches an ASGI scope.

    Uses FastAPI/Starlette's own matching (``route.matches(scope)``), so the
    returned path template is exactly the path as registered on the app, e.g.
    ``("GET", "/gmail/v1/users/{userId}/messages")``. Returns None when no
    route fully matches (unknown path, or method not allowed on the path).
    """
    if scope.get("type") != "http":
        return None
    method = str(scope.get("method", "GET")).upper()
    routes = getattr(app, "routes", None) or []
    for route in routes:
        try:
            match, _child_scope = route.matches(scope)
        except Exception:
            continue
        if match == Match.FULL:
            path = getattr(route, "path", None)
            if path is None:
                continue
            return (method, path)
    return None

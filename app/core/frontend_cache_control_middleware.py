from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_NO_CACHE_VALUE = "no-store, no-cache, must-revalidate, max-age=0"


class FrontendCacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        path = request.url.path.lower()

        if self._should_disable_cache(path):
            response.headers["Cache-Control"] = _NO_CACHE_VALUE
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response

    @staticmethod
    def _should_disable_cache(path: str) -> bool:
        if path in {"/", "/login", "/admin"}:
            return True
        if path.endswith(".html"):
            return True
        if path.startswith("/static/") and (path.endswith(".js") or path.endswith(".css")):
            return True
        return False

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings


async def check_browser_origin(request: Request, call_next):
    """Reject cross-origin writes, including simple form POSTs that bypass CORS."""
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        origin = request.headers.get("origin")
        if (origin and origin.rstrip("/") != settings.frontend_origin.rstrip("/")) or (
            not origin and request.headers.get("sec-fetch-site") == "cross-site"
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "untrusted_origin",
                    "message": "Request origin is not allowed.",
                    "details": None,
                },
            )
    return await call_next(request)

"""Serve SPA deep links while preserving missing asset/API errors."""
from starlette.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or scope["method"] not in {"GET", "HEAD"}:
                raise
            if path.startswith("api/") or path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)

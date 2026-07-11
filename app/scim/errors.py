from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .constants import SCIM_BASE_PATH, SCIM_MEDIA_TYPE
from .schemas import ScimErrorResponse


def scim_error_response(
    *,
    status_code: int,
    detail: str,
    scim_type: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error = ScimErrorResponse(
        detail=detail,
        status=str(status_code),
        scimType=scim_type,
    )
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(exclude_none=True),
        media_type=SCIM_MEDIA_TYPE,
        headers=headers,
    )


def scim_error_response_spec(status_code: int, description: str) -> dict[str, Any]:
    return {
        "model": ScimErrorResponse,
        "description": description,
        "content": {
            SCIM_MEDIA_TYPE: {
                "example": {
                    "schemas": [
                        "urn:ietf:params:scim:api:messages:2.0:Error"
                    ],
                    "detail": description,
                    "status": str(status_code),
                }
            }
        },
    }


SCIM_ERROR_RESPONSES = {
    400: scim_error_response_spec(400, "Bad SCIM request"),
    401: scim_error_response_spec(401, "Authentication required"),
    403: scim_error_response_spec(403, "Insufficient privileges"),
    404: scim_error_response_spec(404, "SCIM resource not found"),
    409: scim_error_response_spec(409, "SCIM resource conflict"),
    500: scim_error_response_spec(500, "Internal SCIM server error"),
}


async def scim_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if not request.url.path.startswith(SCIM_BASE_PATH):
        return await http_exception_handler(request, exc)

    detail = exc.detail if isinstance(exc.detail, str) else "SCIM request failed"
    return scim_error_response(
        status_code=exc.status_code,
        detail=detail,
        headers=exc.headers,
    )


def register_scim_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, scim_http_exception_handler)

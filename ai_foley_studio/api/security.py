"""Bearer-token enforcement for all job and artifact operations."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ai_foley_studio.api.errors import ApiError
from ai_foley_studio.api.schemas import ErrorCode


_bearer = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


def require_api_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    expected = request.app.state.runtime.settings.bearer_token
    if not expected:
        raise ApiError(503, ErrorCode.WORKER_UNAVAILABLE.value, "API authentication is not configured.")
    provided = credentials.credentials if credentials is not None else ""
    if credentials is None or credentials.scheme.casefold() != "bearer" or not secrets.compare_digest(provided, expected):
        raise ApiError(401, ErrorCode.UNAUTHORIZED.value, "A valid bearer token is required.")

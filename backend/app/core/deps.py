"""FastAPI dependencies: database session, authenticated user, RBAC guards."""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, PermissionDenied
from app.core.rbac import Perm, permissions_for
from app.core.security import decode_token
from app.db.models.user import User
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        # Also read the header directly, so this dependency behaves identically
        # when invoked manually (the binary-streaming routes accept either a
        # signed link or a normal session).
        header = request.headers.get("authorization", "")
        scheme, _, value = header.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            token = value.strip()
    if not token:
        # Supports the Next.js server-side proxy, which forwards the token in a
        # httpOnly cookie rather than a header.
        token = request.cookies.get("veridoc_access")
    if not token:
        raise AuthenticationError("No credentials were supplied.")

    payload = decode_token(token, expected_type="access")
    user = db.execute(
        select(User).where(User.id == payload["sub"], User.deleted_at.is_(None))
    ).scalar_one_or_none()
    if user is None:
        raise AuthenticationError("The account for this session no longer exists.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")
    request.state.actor = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(*perms: Perm) -> Callable[[User], User]:
    """Server-side authorisation. Every mutating route declares its permission."""

    def guard(user: CurrentUser) -> User:
        granted = permissions_for(user.role_name)
        missing = [p for p in perms if p not in granted]
        if missing:
            raise PermissionDenied(
                f"Role '{user.role_name}' lacks the required permission(s): "
                f"{', '.join(missing)}.",
                details={"required": [str(p) for p in perms],
                         "role": user.role_name},
            )
        return user

    return guard


def request_context(request: Request) -> dict:
    return {
        "ip_address": getattr(request.state, "client_ip", None),
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


RequestContext = Annotated[dict, Depends(request_context)]

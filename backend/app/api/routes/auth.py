from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, RequestContext
from app.core.errors import AuthenticationError, ValidationFailure
from app.core.ratelimit import limiter
from app.core.rbac import ROLE_LABELS, permissions_for
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.enums import AuditAction
from app.db.models.user import RoleDefinition, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RoleOut,
    TokenResponse,
    UserOut,
)
from app.schemas.common import Acknowledgement
from app.services import audit

router = APIRouter(prefix="/auth", tags=["authentication"])

MAX_FAILED_LOGINS = 6
LOCKOUT_MINUTES = 15


def user_payload(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, full_name=user.full_name, role_name=user.role_name,
        role_label=ROLE_LABELS.get(user.role_name, user.role_name), job_title=user.job_title,
        team=user.team, is_active=user.is_active,
        must_change_password=user.must_change_password, last_login_at=user.last_login_at,
        created_at=user.created_at,
        permissions=sorted(str(p) for p in permissions_for(user.role_name)),
        initials=user.initials,
    )


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for tokens")
def login(payload: LoginRequest, request: Request, db: DbSession, ctx: RequestContext):
    limiter.check(f"login:{ctx['ip_address']}", settings.rate_limit_login)
    limiter.check(f"login-user:{payload.email.lower()}", settings.rate_limit_login)

    user = db.execute(
        select(User).where(User.email == payload.email.lower(), User.deleted_at.is_(None))
    ).scalar_one_or_none()

    def fail(reason: str):
        audit.record(
            db, action=AuditAction.USER_LOGIN_FAILED, resource_type="user",
            resource_id=user.id if user else None,
            summary=f"Failed sign-in for {payload.email}: {reason}",
            metadata={"reason": reason, "email_attempted": payload.email}, **ctx,
        )
        db.commit()
        # Deliberately identical message for unknown user and wrong password.
        raise AuthenticationError("Email address or password is incorrect.")

    if user is None:
        fail("unknown_account")
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise AuthenticationError(
            f"This account is temporarily locked until "
            f"{user.locked_until.strftime('%H:%M UTC')} after repeated failed attempts."
        )
    if not user.is_active:
        fail("inactive_account")
    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        fail("bad_password")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    access, expires = create_token(user.id, user.role_name, "access")
    refresh, _ = create_token(user.id, user.role_name, "refresh")
    audit.record(
        db, action=AuditAction.USER_LOGIN, resource_type="user", resource_id=user.id, actor=user,
        summary=f"{user.email} signed in.", metadata={"role": user.role_name}, **ctx,
    )
    return TokenResponse(
        access_token=access, refresh_token=refresh, expires_at=expires, user=user_payload(user)
    )


@router.post("/refresh", response_model=TokenResponse, summary="Rotate an access token")
def refresh_token(payload: RefreshRequest, db: DbSession, ctx: RequestContext):
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    user = db.execute(
        select(User).where(User.id == claims["sub"], User.deleted_at.is_(None))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("This session can no longer be refreshed.")
    access, expires = create_token(user.id, user.role_name, "access", session_id=claims.get("sid"))
    rotated, _ = create_token(user.id, user.role_name, "refresh", session_id=claims.get("sid"))
    return TokenResponse(
        access_token=access, refresh_token=rotated, expires_at=expires, user=user_payload(user)
    )


@router.post("/logout", response_model=Acknowledgement, summary="Record a sign-out")
def logout(user: CurrentUser, db: DbSession, ctx: RequestContext):
    audit.record(
        db, action=AuditAction.USER_LOGOUT, resource_type="user", resource_id=user.id, actor=user,
        summary=f"{user.email} signed out.", **ctx,
    )
    return Acknowledgement(message="Signed out. Discard the tokens on the client.")


@router.get("/me", response_model=UserOut, summary="Current user and effective permissions")
def me(user: CurrentUser):
    return user_payload(user)


@router.post("/change-password", response_model=Acknowledgement, summary="Change own password")
def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, db: DbSession, ctx: RequestContext
):
    if not verify_password(payload.current_password, user.password_hash):
        raise ValidationFailure("The current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise ValidationFailure("The new password must differ from the current one.")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    audit.record(
        db, action=AuditAction.USER_UPDATED, resource_type="user", resource_id=user.id, actor=user,
        summary=f"{user.email} changed their password.",
        after={"password_changed": True}, **ctx,
    )
    return Acknowledgement(message="Password updated.")


@router.get("/roles", response_model=list[RoleOut], summary="Role catalogue")
def roles(db: DbSession, user: CurrentUser):
    rows = db.execute(select(RoleDefinition).order_by(RoleDefinition.name)).scalars().all()
    return [
        RoleOut(name=r.name, label=r.label, description=r.description,
                permissions=sorted(r.permissions or []))
        for r in rows
    ]

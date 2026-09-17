from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select

from app.api.routes.auth import user_payload
from app.core.deps import DbSession, RequestContext, require
from app.core.errors import ConflictError, NotFoundError, ValidationFailure
from app.core.rbac import Perm
from app.core.security import hash_password
from app.db.enums import AuditAction
from app.db.models.investigation import Investigation
from app.db.models.user import RoleDefinition, User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import Page, page_meta
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut], summary="List platform users")
def list_users(
    db: DbSession, user: Annotated[User, Depends(require(Perm.USER_READ))],
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    role: str | None = None, active: bool | None = None,
    search: str | None = Query(None, max_length=120),
):
    query = select(User).where(User.deleted_at.is_(None))
    if role:
        query = query.where(User.role_name == role)
    if active is not None:
        query = query.where(User.is_active.is_(active))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(User.email.ilike(like), User.full_name.ilike(like)))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(
        query.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[UserOut](items=[user_payload(u) for u in rows],
                         meta=page_meta(int(total), page, page_size))


@router.get("/investigators", response_model=list[UserOut],
            summary="Investigators available for assignment")
def investigators(db: DbSession, user: Annotated[User, Depends(require(Perm.CLAIM_READ))]):
    from app.core.rbac import Role

    rows = db.execute(
        select(User).where(User.role_name.in_([Role.FRAUD_INVESTIGATOR, Role.REVIEWER]),
                           User.is_active.is_(True), User.deleted_at.is_(None))
        .order_by(User.full_name)
    ).scalars().all()
    return [user_payload(u) for u in rows]


@router.get("/workload", summary="Investigator workload")
def workload(db: DbSession, user: Annotated[User, Depends(require(Perm.INVESTIGATION_READ))]):
    rows = db.execute(
        select(User.id, User.full_name, User.email, func.count(Investigation.id))
        .join(Investigation, Investigation.assigned_to_id == User.id, isouter=True)
        .where(User.deleted_at.is_(None), User.is_active.is_(True))
        .group_by(User.id, User.full_name, User.email)
        .order_by(func.count(Investigation.id).desc())
    ).all()
    return {"items": [
        {"user_id": r[0], "full_name": r[1], "email": r[2], "assigned_investigations": int(r[3])}
        for r in rows
    ]}


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             summary="Create a user")
def create_user(
    payload: UserCreate, db: DbSession, ctx: RequestContext,
    actor: Annotated[User, Depends(require(Perm.USER_WRITE))],
):
    email = payload.email.lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise ConflictError("A user with that email already exists.")
    if db.execute(
        select(RoleDefinition).where(RoleDefinition.name == payload.role_name)
    ).scalar_one_or_none() is None:
        raise ValidationFailure(f"Unknown role '{payload.role_name}'.")
    user = User(
        email=email, full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password), role_name=payload.role_name,
        job_title=payload.job_title, team=payload.team, is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    audit.record(
        db, action=AuditAction.USER_CREATED, resource_type="user", resource_id=user.id,
        actor=actor, summary=f"User {email} created with role {payload.role_name}.",
        after={"email": email, "role_name": payload.role_name,
               "must_change_password": True}, **ctx,
    )
    db.commit()
    db.refresh(user)
    return user_payload(user)


@router.patch("/{user_id}", response_model=UserOut, summary="Update a user")
def update_user(
    user_id: str, payload: UserUpdate, db: DbSession, ctx: RequestContext,
    actor: Annotated[User, Depends(require(Perm.USER_WRITE))],
):
    user = db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("The user does not exist.")
    data = payload.model_dump(exclude_unset=True)
    reset = data.pop("reset_password", None)
    if data.get("role_name") and db.execute(
        select(RoleDefinition).where(RoleDefinition.name == data["role_name"])
    ).scalar_one_or_none() is None:
        raise ValidationFailure(f"Unknown role '{data['role_name']}'.")
    if user.id == actor.id and data.get("is_active") is False:
        raise ValidationFailure("You cannot deactivate your own account.")
    before = {k: getattr(user, k) for k in data}
    for key, value in data.items():
        setattr(user, key, value)
    if reset:
        from app.core.security import password_strength_errors

        errors = password_strength_errors(reset)
        if errors:
            raise ValidationFailure(" ".join(errors))
        user.password_hash = hash_password(reset)
        user.must_change_password = True
        user.failed_login_count = 0
        user.locked_until = None
    audit.record(
        db, action=AuditAction.USER_UPDATED, resource_type="user", resource_id=user.id,
        actor=actor, summary=f"User {user.email} updated ({', '.join(data) or 'password reset'}).",
        before={k: str(v) for k, v in before.items()},
        after={**{k: str(v) for k, v in data.items()},
               **({"password_reset": True} if reset else {})}, **ctx,
    )
    db.commit()
    db.refresh(user)
    return user_payload(user)


@router.get("/{user_id}", response_model=UserOut, summary="User detail")
def get_user(user_id: str, db: DbSession,
             actor: Annotated[User, Depends(require(Perm.USER_READ))]):
    user = db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("The user does not exist.")
    return user_payload(user)

"""Admin surface: detection rules, provider configuration and system settings."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DbSession, RequestContext, require
from app.core.errors import NotFoundError, ValidationFailure
from app.core.rbac import Perm
from app.db.enums import AuditAction, ProviderKind
from app.db.models.config import DetectionRule, ProviderConfig, SystemSetting
from app.db.models.user import User
from app.schemas.admin import (
    ProviderOut,
    ProviderUpdate,
    RuleOut,
    RuleUpdate,
    SettingOut,
    SettingUpdate,
)
from app.services import audit
from app.services.aigc.factory import list_aigc_providers
from app.services.consistency.engine import rule_catalogue
from app.services.ocr.factory import list_ocr_providers
from app.services.risk.engine import CATEGORY_CAPS, DEFAULT_THRESHOLDS, weight_catalogue
from app.services.verification.factory import list_verification_providers

router = APIRouter(tags=["administration"])


# ------------------------------------------------------------------- rules
@router.get("/rules", response_model=list[RuleOut], summary="Detection rule catalogue")
def list_rules(db: DbSession, user: Annotated[User, Depends(require(Perm.RULE_READ))],
               category: str | None = None, enabled: bool | None = None):
    query = select(DetectionRule)
    if category:
        query = query.where(DetectionRule.category == category)
    if enabled is not None:
        query = query.where(DetectionRule.enabled.is_(enabled))
    rows = db.execute(query.order_by(DetectionRule.category, DetectionRule.code)).scalars().all()
    return [RuleOut.model_validate(r) for r in rows]


@router.get("/rules/catalogue", summary="Built-in rule definitions and risk weights")
def rules_catalogue(user: Annotated[User, Depends(require(Perm.RULE_READ))]):
    return {
        "consistency_rules": rule_catalogue(),
        "risk_weight_defaults": weight_catalogue(),
        "category_caps": CATEGORY_CAPS,
        "default_thresholds": DEFAULT_THRESHOLDS,
        "note": ("Weights and severities stored in the rules table override these defaults at "
                 "run time; the risk engine reads them on every assessment."),
    }


@router.patch("/rules/{code}", response_model=RuleOut, summary="Tune a detection rule")
def update_rule(
    code: str, payload: RuleUpdate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.RULE_WRITE))],
):
    rule = db.execute(select(DetectionRule).where(DetectionRule.code == code)).scalar_one_or_none()
    if rule is None:
        raise NotFoundError(f"No rule with code '{code}'.")
    data = payload.model_dump(exclude_unset=True)
    before = {k: getattr(rule, k) for k in data}
    for key, value in data.items():
        setattr(rule, key, value)
    rule.updated_by_id = user.id
    audit.record(
        db, action=AuditAction.RULE_UPDATED, resource_type="detection_rule", resource_id=rule.code,
        actor=user, summary=f"Rule {code} updated ({', '.join(data)}).",
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in data.items()},
        metadata={"affects": "consistency engine and risk weighting"}, **ctx,
    )
    db.commit()
    db.refresh(rule)
    return RuleOut.model_validate(rule)


@router.get("/document-types", summary="Document type catalogue and extraction schemas")
def document_types(user: Annotated[User, Depends(require(Perm.RULE_READ))]):
    """The document taxonomy, as the classifier and the extractor actually see it.

    Adding a document type (or a locale's wording for an existing one) is a data
    change in ``extract/schema.py`` and ``classify/taxonomy.py`` - this endpoint
    exposes the resulting contract so an administrator can see exactly which
    fields a type requires and which verification routes depend on them.
    """
    from app.db.enums import DOCUMENT_TYPE_LABELS
    from app.services.classify.taxonomy import SIGNATURES
    from app.services.extract.schema import SCHEMAS
    from app.services.verification.factory import PLAN_BY_DOCUMENT_TYPE

    out = []
    for key, label in DOCUMENT_TYPE_LABELS.items():
        schema = SCHEMAS.get(key)
        signature = SIGNATURES.get(key)
        out.append({
            "document_type": key,
            "label": label,
            "schema_label": schema.label if schema else None,
            "field_count": len(schema.field_keys) if schema else 0,
            "required_fields": schema.required_keys() if schema else [],
            "fields": [
                {"key": field.key, "label": field.label, "type": field.value_type,
                 "group": field.group, "sensitive": field.sensitive,
                 "required": schema.is_required(field.key) if schema else False,
                 "labels": list(field.labels)}
                for field in (schema.fields if schema else [])
            ],
            "line_items": schema.line_items if schema else False,
            "verification_routes": PLAN_BY_DOCUMENT_TYPE.get(key, []),
            "classifier_signature": None if signature is None else {
                "strong_terms": list(signature.strong),
                "supporting_terms": list(signature.supporting),
                "expects_line_items": signature.expects_line_items,
                "expects_totals": signature.expects_totals,
                "typical_pages": list(signature.typical_pages),
            },
        })
    return {
        "document_types": out,
        "note": ("Field extraction is schema-driven: a type is a list of declared fields with "
                 "their label synonyms, so nothing in the extractor is hard-coded around one "
                 "sample document."),
    }


# --------------------------------------------------------------- providers
@router.get("/providers", response_model=list[ProviderOut], summary="Provider configuration")
def list_providers(db: DbSession, user: Annotated[User, Depends(require(Perm.PROVIDER_READ))],
                   kind: str | None = None):
    query = select(ProviderConfig)
    if kind:
        query = query.where(ProviderConfig.kind == kind)
    rows = db.execute(query.order_by(ProviderConfig.kind, ProviderConfig.key)).scalars().all()
    return [ProviderOut.model_validate(r) for r in rows]


@router.get("/providers/runtime", summary="Live provider availability")
def provider_runtime(user: Annotated[User, Depends(require(Perm.PROVIDER_READ))]):
    return {
        "ocr": {"configured": settings.ocr_provider, "providers": list_ocr_providers()},
        "aigc": {"configured": settings.aigc_provider, "providers": list_aigc_providers()},
        "verification": {"configured": settings.verification_provider,
                         "providers": list_verification_providers()},
        "storage": {"configured": settings.storage_provider},
        "malware": {"configured": settings.malware_scanner},
        "credentials_note": ("Secrets are read from environment variables only. This screen "
                             "shows which variable names a provider expects - never the values."),
    }


@router.patch("/providers/{kind}/{key}", response_model=ProviderOut,
              summary="Activate or configure a provider")
def update_provider(
    kind: str, key: str, payload: ProviderUpdate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.PROVIDER_WRITE))],
):
    if kind not in set(ProviderKind):
        raise ValidationFailure(f"Unknown provider kind '{kind}'.")
    provider = db.execute(
        select(ProviderConfig).where(ProviderConfig.kind == kind, ProviderConfig.key == key)
    ).scalar_one_or_none()
    if provider is None:
        raise NotFoundError(f"No {kind} provider with key '{key}'.")
    data = payload.model_dump(exclude_unset=True)
    before = {k: getattr(provider, k) for k in data}
    if data.get("is_active"):
        # Exactly one provider per kind is active at a time.
        for other in db.execute(
            select(ProviderConfig).where(ProviderConfig.kind == kind,
                                         ProviderConfig.key != key)
        ).scalars().all():
            other.is_active = False
    for field, value in data.items():
        setattr(provider, field, value)
    provider.updated_by_id = user.id
    audit.record(
        db, action=AuditAction.PROVIDER_UPDATED, resource_type="provider_config",
        resource_id=f"{kind}:{key}", actor=user,
        summary=f"Provider {kind}/{key} updated ({', '.join(data)}).",
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in data.items()},
        metadata={"is_demo": provider.is_demo}, **ctx,
    )
    db.commit()
    db.refresh(provider)
    # Provider factories cache their selection per process.
    from app.services.aigc.factory import _from_db as aigc_cache_probe  # noqa: F401
    return ProviderOut.model_validate(provider)


# ---------------------------------------------------------------- settings
@router.get("/settings", response_model=list[SettingOut], summary="System settings")
def list_settings(db: DbSession, user: Annotated[User, Depends(require(Perm.SETTINGS_READ))]):
    rows = db.execute(select(SystemSetting).order_by(SystemSetting.key)).scalars().all()
    return [SettingOut.model_validate(r) for r in rows]


@router.put("/settings/{key}", response_model=SettingOut, summary="Update a system setting")
def update_setting(
    key: str, payload: SettingUpdate, db: DbSession, ctx: RequestContext,
    user: Annotated[User, Depends(require(Perm.SETTINGS_WRITE))],
):
    setting = db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    ).scalar_one_or_none()
    if setting is None:
        raise NotFoundError(f"No setting with key '{key}'.")
    if key == "risk_thresholds":
        value = payload.value or {}
        try:
            review = int(value["review_recommended"])
            high = int(value["high_concern"])
        except (KeyError, TypeError, ValueError):
            raise ValidationFailure(
                "risk_thresholds requires integer 'review_recommended' and 'high_concern'."
            ) from None
        if not 0 < review < high <= 100:
            raise ValidationFailure(
                "Thresholds must satisfy 0 < review_recommended < high_concern <= 100."
            )
    before = setting.value
    setting.value = payload.value
    setting.updated_by_id = user.id
    audit.record(
        db, action=AuditAction.SETTING_UPDATED, resource_type="system_setting", resource_id=key,
        actor=user, summary=f"Setting '{key}' updated.",
        before={"value": before}, after={"value": payload.value}, **ctx,
    )
    db.commit()
    db.refresh(setting)
    return SettingOut.model_validate(setting)

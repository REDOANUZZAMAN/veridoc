"""Consistency engine runner.

Reads effective rule configuration (enabled / severity / weight / params) so an
administrator can retune the engine without a deploy, executes every applicable
rule, and returns both the failures *and* the checks that passed - the UI shows
green ticks for passed checks, which is what makes a "low concern" verdict
meaningful rather than merely empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.config import RULES_VERSION
from app.core.logging import get_logger
from app.services.consistency.rules import (
    REGISTRY,
    RuleContext,
    RuleDefinition,
    rules_for,
)
from app.services.extract.engine import ExtractionResult
from app.services.forensics.base import RawFinding

logger = get_logger(__name__)


@dataclass(slots=True)
class CheckOutcome:
    code: str
    name: str
    status: str            # passed | failed | not_applicable | disabled | error
    severity: str
    weight: float
    detail: str = ""
    finding_count: int = 0

    def as_dict(self) -> dict:
        return {
            "code": self.code, "name": self.name, "status": self.status,
            "severity": self.severity, "weight": self.weight, "detail": self.detail,
            "finding_count": self.finding_count,
        }


@dataclass(slots=True)
class ConsistencyReport:
    findings: list[RawFinding] = field(default_factory=list)
    checks: list[CheckOutcome] = field(default_factory=list)
    rules_version: str = RULES_VERSION

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "passed")

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "failed")

    def summary(self) -> dict:
        return {
            "rules_version": self.rules_version,
            "rules_evaluated": sum(1 for c in self.checks
                                   if c.status in {"passed", "failed"}),
            "passed": self.passed_count,
            "failed": self.failed_count,
            "not_applicable": sum(1 for c in self.checks if c.status == "not_applicable"),
            "disabled": sum(1 for c in self.checks if c.status == "disabled"),
            "errors": sum(1 for c in self.checks if c.status == "error"),
            "checks": [c.as_dict() for c in self.checks],
        }


def effective_config(rule: RuleDefinition, overrides: dict[str, dict] | None) -> dict:
    override = (overrides or {}).get(rule.code, {})
    params = {**rule.params, **(override.get("params") or {})}
    return {
        "enabled": override.get("enabled", True),
        "severity": override.get("severity", rule.default_severity),
        "weight": float(override.get("weight", rule.weight)),
        "params": params,
        "version": override.get("version", rule.version),
    }


def run_consistency(
    extraction: ExtractionResult,
    *,
    document_type: str,
    page_texts: dict[int, str] | None = None,
    required_keys: list[str] | None = None,
    rule_overrides: dict[str, dict] | None = None,
    today: date | None = None,
) -> ConsistencyReport:
    ctx = RuleContext(
        document_type=document_type,
        fields=extraction.by_key(),
        line_items=extraction.line_items,
        page_texts=page_texts or {},
        required_keys=required_keys or extraction.missing_required,
        today=today or date.today(),
        currency=extraction.stats.get("currency"),
    )
    report = ConsistencyReport()
    applicable = {r.code for r in rules_for(document_type)}

    for rule in REGISTRY:
        cfg = effective_config(rule, rule_overrides)
        if rule.code not in applicable:
            report.checks.append(CheckOutcome(
                rule.code, rule.name, "not_applicable", cfg["severity"], cfg["weight"],
                detail=f"Not applicable to document type '{document_type}'.",
            ))
            continue
        if not cfg["enabled"]:
            report.checks.append(CheckOutcome(
                rule.code, rule.name, "disabled", cfg["severity"], cfg["weight"],
                detail="Disabled in the rule configuration.",
            ))
            continue
        try:
            result = rule.fn(ctx, cfg)
        except Exception as exc:  # a broken rule must not fail the whole run
            logger.warning("consistency_rule_error",
                           extra={"rule": rule.code, "detail": str(exc)[:160]})
            report.checks.append(CheckOutcome(
                rule.code, rule.name, "error", cfg["severity"], cfg["weight"],
                detail=f"Rule raised {type(exc).__name__}.",
            ))
            continue
        if result is None:
            report.checks.append(CheckOutcome(
                rule.code, rule.name, "not_applicable", cfg["severity"], cfg["weight"],
                detail="Required inputs were not present on this document.",
            ))
        elif not result:
            report.checks.append(CheckOutcome(
                rule.code, rule.name, "passed", cfg["severity"], cfg["weight"],
                detail="Check passed.",
            ))
        else:
            for finding in result:
                finding.extras.setdefault("rule_weight", cfg["weight"])
            report.findings.extend(result)
            report.checks.append(CheckOutcome(
                rule.code, rule.name, "failed", cfg["severity"], cfg["weight"],
                detail=result[0].title, finding_count=len(result),
            ))
    return report


def rule_catalogue() -> list[dict]:
    return [
        {
            "code": r.code, "name": r.name, "description": r.description,
            "category": "consistency", "default_severity": r.default_severity,
            "weight": r.weight, "applies_to": list(r.applies_to), "params": r.params,
            "version": r.version,
        }
        for r in REGISTRY
    ]

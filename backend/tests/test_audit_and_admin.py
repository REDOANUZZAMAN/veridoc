"""Audit-trail integrity, admin configuration and privacy controls."""
from __future__ import annotations

from sqlalchemy import select

from app.core.logging import redact
from app.db.models.audit import AuditLog
from app.services import audit
from tests.conftest import auth


def test_chain_links_each_entry_to_the_previous(db):
    first = audit.record(db, action="test.one", resource_type="test", resource_id="1",
                         summary="first")
    second = audit.record(db, action="test.two", resource_type="test", resource_id="2",
                          summary="second")
    db.commit()
    assert second.prev_hash == first.entry_hash
    assert second.entry_hash != first.entry_hash
    assert audit.verify_chain(db)["intact"] is True


def test_rewriting_history_breaks_the_chain(db):
    audit.record(db, action="test.three", resource_type="test", resource_id="3",
                 summary="before")
    db.commit()
    row = db.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).scalar_one()
    row.summary = "tampered after the fact"
    db.commit()

    result = audit.verify_chain(db)
    assert result["intact"] is False
    assert result["broken_at"]["seq"] == row.seq
    assert result["broken_at"]["recomputed_entry_hash"] != row.entry_hash

    # Restore so later tests see an intact chain.
    row.summary = "before"
    db.commit()
    assert audit.verify_chain(db)["intact"] is True


def test_sensitive_values_are_redacted_before_storage(db):
    entry = audit.record(
        db, action="test.pii", resource_type="test", resource_id="4",
        before={"patient_name": "Amelia R. Okonkwo", "raw_text": "full medical record text"},
        after={"diagnosis": "confidential", "total": "4820.00"},
        metadata={"password": "hunter2", "note": "contact a.okonkwo@example.com"},
    )
    db.commit()
    assert entry.before_state["patient_name"] == "[redacted]"
    assert entry.before_state["raw_text"] == "[redacted]"
    assert entry.after_state["diagnosis"] == "[redacted]"
    assert entry.after_state["total"] == "4820.00"
    assert entry.metadata_json["password"] == "[redacted]"


def test_log_formatter_redacts_pii():
    scrubbed = redact({"email": "person@example.com", "policy": "POL-938472",
                       "nested": ["card 4111111111111111"]})
    assert "person@example.com" not in str(scrubbed)
    assert "4111111111111111" not in str(scrubbed)


def test_audit_actions_endpoint_lists_known_actions(client, admin_token):
    body = client.get("/api/audit-logs/actions", headers=auth(admin_token)).json()
    assert "document.uploaded" in body["actions"]
    assert "review.action" in body["actions"]


# ------------------------------------------------------------------- admin
def test_rules_are_listed_with_weights(client, admin_token):
    rules = client.get("/api/rules", headers=auth(admin_token)).json()
    assert len(rules) > 50
    codes = {rule["code"] for rule in rules}
    assert "LINE_ITEM_SUM_MISMATCH" in codes
    assert "VERIFY_POLICY_LOOKUP_MISMATCH" in codes
    assert all(rule["weight"] >= 0 for rule in rules)


def test_rule_can_be_retuned_and_the_change_is_audited(client, admin_token):
    response = client.patch("/api/rules/DUPLICATE_LINE_ITEMS",
                            json={"weight": 11.5, "default_severity": "medium"},
                            headers=auth(admin_token))
    assert response.status_code == 200
    assert response.json()["weight"] == 11.5

    logs = client.get("/api/audit-logs",
                      params={"action": "rule.updated", "page_size": 5},
                      headers=auth(admin_token)).json()
    assert logs["items"][0]["resource_id"] == "DUPLICATE_LINE_ITEMS"


def test_rule_catalogue_exposes_the_risk_model(client, admin_token):
    body = client.get("/api/rules/catalogue", headers=auth(admin_token)).json()
    assert body["consistency_rules"]
    assert body["risk_weight_defaults"]
    assert body["category_caps"]["verification"] > body["category_caps"]["aigc"]
    assert body["default_thresholds"]["high_concern"] > body["default_thresholds"]["review_recommended"]


def test_providers_never_expose_credential_values(client, admin_token):
    providers = client.get("/api/providers", headers=auth(admin_token)).json()
    remote = next(p for p in providers if p["key"] == "remote_http" and p["kind"] == "aigc")
    assert remote["credential_env_keys"] == ["AIGC_REMOTE_URL", "AIGC_REMOTE_API_KEY"]
    serialised = str(providers)
    assert "secret" not in serialised.lower() or "S3_SECRET_ACCESS_KEY" in serialised
    demo = next(p for p in providers if p["key"] == "demo_heuristic")
    assert demo["is_demo"] is True and demo["is_active"] is True


def test_activating_a_provider_deactivates_the_others_of_its_kind(client, admin_token):
    response = client.patch("/api/providers/ocr/tesseract", json={"is_active": True},
                            headers=auth(admin_token))
    assert response.status_code == 200
    providers = client.get("/api/providers", params={"kind": "ocr"},
                           headers=auth(admin_token)).json()
    active = [p for p in providers if p["is_active"]]
    assert len(active) == 1 and active[0]["key"] == "tesseract"
    # restore the default
    client.patch("/api/providers/ocr/hybrid", json={"is_active": True},
                 headers=auth(admin_token))


def test_provider_runtime_reports_availability(client, admin_token):
    body = client.get("/api/providers/runtime", headers=auth(admin_token)).json()
    assert body["ocr"]["providers"]
    assert body["aigc"]["configured"]
    assert "environment variables" in body["credentials_note"]


def test_risk_thresholds_are_validated(client, admin_token):
    bad = client.put("/api/settings/risk_thresholds",
                     json={"value": {"review_recommended": 90, "high_concern": 40}},
                     headers=auth(admin_token))
    assert bad.status_code == 422

    good = client.put("/api/settings/risk_thresholds",
                      json={"value": {"review_recommended": 40, "high_concern": 75}},
                      headers=auth(admin_token))
    assert good.status_code == 200
    assert good.json()["value"]["high_concern"] == 75


def test_settings_are_listed_with_descriptions(client, admin_token):
    settings_list = client.get("/api/settings", headers=auth(admin_token)).json()
    keys = {item["key"] for item in settings_list}
    assert {"risk_thresholds", "retention", "review_policy", "privacy_policy"} <= keys
    assert all(item["description"] for item in settings_list)


def test_user_creation_and_role_change_are_audited(client, admin_token):
    created = client.post(
        "/api/users",
        json={"email": "new.reviewer@veridoc.example", "full_name": "New Reviewer",
              "role_name": "reviewer", "password": "Str0ng!Password1",
              "job_title": "Reviewer"},
        headers=auth(admin_token),
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assert user["must_change_password"] is True

    updated = client.patch(f"/api/users/{user['id']}",
                           json={"role_name": "claims_officer"},
                           headers=auth(admin_token))
    assert updated.status_code == 200
    assert updated.json()["role_name"] == "claims_officer"

    logs = client.get("/api/audit-logs", params={"action": "user.created", "page_size": 5},
                      headers=auth(admin_token)).json()
    assert any(entry["resource_id"] == user["id"] for entry in logs["items"])


def test_unknown_role_is_rejected(client, admin_token):
    response = client.post(
        "/api/users",
        json={"email": "bad.role@veridoc.example", "full_name": "Bad Role",
              "role_name": "superuser", "password": "Str0ng!Password1"},
        headers=auth(admin_token),
    )
    assert response.status_code == 422


def test_ready_probe_reports_components(client):
    body = client.get("/api/ready").json()
    assert body["components"]["database"]["healthy"] is True
    assert body["components"]["storage"]["provider"]
    assert body["components"]["queue"]["mode"] in ("inline", "redis")
    assert body["versions"]["rules"]

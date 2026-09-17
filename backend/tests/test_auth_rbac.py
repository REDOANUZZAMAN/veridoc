"""Authentication and role-based access control."""
from __future__ import annotations

import pytest

from app.core.rbac import Perm, Role, has_permission, permissions_for
from tests.conftest import auth, login


def test_login_returns_token_and_permissions(client):
    body = login(client, "investigator@veridoc.example")
    assert body["token_type"] == "bearer"
    assert body["user"]["role_name"] == "fraud_investigator"
    assert "finding:confirm" in body["user"]["permissions"]
    assert "rule:write" not in body["user"]["permissions"]


def test_login_rejects_wrong_password_without_disclosing_account(client):
    unknown = client.post("/api/auth/login",
                          json={"email": "nobody@veridoc.example", "password": "whatever"})
    wrong = client.post("/api/auth/login",
                        json={"email": "admin@veridoc.example", "password": "wrong-password"})
    assert unknown.status_code == wrong.status_code == 401
    # Identical wording: the response must not reveal whether the account exists.
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_protected_endpoint_requires_a_token(client):
    assert client.get("/api/documents").status_code == 401


def test_invalid_token_is_rejected(client):
    response = client.get("/api/documents", headers=auth("not-a-real-token"))
    assert response.status_code == 401


def test_me_reflects_effective_permissions(client, reviewer_token):
    body = client.get("/api/auth/me", headers=auth(reviewer_token)).json()
    assert body["role_name"] == "reviewer"
    assert "finding:dismiss" in body["permissions"]
    assert "investigation:escalate" not in body["permissions"]
    assert "claim:decide" not in body["permissions"]


def test_change_password_enforces_strength(client, reviewer_token):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "Demo!2026", "new_password": "weak"},
        headers=auth(reviewer_token),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "role,perm,expected",
    [
        (Role.ADMIN, Perm.RULE_WRITE, True),
        (Role.ADMIN, Perm.USER_WRITE, True),
        (Role.FRAUD_INVESTIGATOR, Perm.FINDING_CONFIRM, True),
        (Role.FRAUD_INVESTIGATOR, Perm.INVESTIGATION_ESCALATE, True),
        (Role.FRAUD_INVESTIGATOR, Perm.RULE_WRITE, False),
        (Role.FRAUD_INVESTIGATOR, Perm.CLAIM_DECIDE, False),
        (Role.CLAIMS_OFFICER, Perm.CLAIM_DECIDE, True),
        (Role.CLAIMS_OFFICER, Perm.FINDING_CONFIRM, False),
        (Role.CLAIMS_OFFICER, Perm.AUDIT_READ, False),
        (Role.REVIEWER, Perm.FINDING_DISMISS, True),
        (Role.REVIEWER, Perm.DOCUMENT_UPLOAD, False),
        (Role.REVIEWER, Perm.VERIFICATION_RUN, False),
    ],
)
def test_permission_matrix(role, perm, expected):
    assert has_permission(role, perm) is expected


def test_every_role_is_read_capable_but_only_admin_is_omnipotent():
    admin = permissions_for(Role.ADMIN)
    for role in Role:
        assert Perm.DASHBOARD_READ in permissions_for(role)
        if role != Role.ADMIN:
            assert permissions_for(role) < admin


def test_non_admin_cannot_write_rules(client, investigator_token):
    response = client.patch("/api/rules/LINE_ITEM_SUM_MISMATCH", json={"weight": 1.0},
                            headers=auth(investigator_token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_non_admin_cannot_create_users(client, claims_token):
    response = client.post(
        "/api/users",
        json={"email": "x@veridoc.example", "full_name": "X Y", "role_name": "reviewer",
              "password": "Str0ng!Password1"},
        headers=auth(claims_token),
    )
    assert response.status_code == 403


def test_claims_officer_cannot_read_audit_log(client, claims_token):
    assert client.get("/api/audit-logs", headers=auth(claims_token)).status_code == 403


def test_admin_can_read_audit_log(client, admin_token):
    assert client.get("/api/audit-logs", headers=auth(admin_token)).status_code == 200


def test_refresh_token_rotates(client):
    body = login(client, "admin@veridoc.example")
    rotated = client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["access_token"] != body["access_token"]


def test_access_token_cannot_be_used_as_refresh_token(client):
    body = login(client, "admin@veridoc.example")
    response = client.post("/api/auth/refresh", json={"refresh_token": body["access_token"]})
    assert response.status_code == 401

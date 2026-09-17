"""The full investigator workflow through the HTTP API."""
from __future__ import annotations

import pytest

from tests.conftest import auth, upload

pytestmark = pytest.mark.slow


@pytest.fixture()
def analysed_document(client, claims_token, tampered_invoice_pdf, make_claim):
    data, mime = tampered_invoice_pdf
    claim = make_claim(claimed_amount="8500.00")
    response = upload(client, claims_token, data, "workflow.pdf", mime, claim["id"],
                      analyze=True)
    assert response.status_code == 201, response.text
    document = response.json()["document"]
    # QUEUE_MODE=inline in tests: the background task runs on response teardown,
    # so trigger a synchronous run to make the state deterministic.
    analyse = client.post(f"/api/documents/{document['id']}/analyze",
                          json={"force": True}, headers=auth(claims_token))
    assert analyse.status_code == 200, analyse.text
    return claim, document["id"]


def test_upload_response_describes_what_happened(client, claims_token, invoice_pdf, make_claim):
    data, mime = invoice_pdf
    claim = make_claim()
    body = upload(client, claims_token, data, "receipt.pdf", mime, claim["id"]).json()
    assert body["document"]["processing_status"] in ("queued", "uploaded")
    assert body["analysis"]["queued"] is True
    assert "preserved unchanged" in body["message"]


def test_documents_list_supports_filtering(client, investigator_token, analysed_document):
    _, document_id = analysed_document
    listing = client.get("/api/documents", params={"risk_band": "high_concern",
                                                   "page_size": 50},
                         headers=auth(investigator_token)).json()
    assert listing["meta"]["total"] >= 1
    assert any(item["id"] == document_id for item in listing["items"])
    assert all(item["risk_band"] == "high_concern" for item in listing["items"])


def test_investigation_payload_contains_every_panel(client, investigator_token,
                                                    analysed_document):
    _, document_id = analysed_document
    detail = client.get(f"/api/documents/{document_id}",
                        headers=auth(investigator_token)).json()
    for key in ("pages", "ocr", "extracted_fields", "line_items", "metadata_entries",
                "findings", "risk_assessment", "latest_run", "verification",
                "review_actions", "schema_fields"):
        assert key in detail, key
    assert detail["risk_assessment"]["band"] in ("low_concern", "review_recommended",
                                                 "high_concern")
    assert detail["risk_assessment"]["top_reasons"]
    assert detail["latest_run"]["stages"]
    assert detail["ocr"][0]["words"]


def test_findings_endpoint_filters_and_labels_provenance(client, investigator_token,
                                                         analysed_document):
    _, document_id = analysed_document
    body = client.get(f"/api/documents/{document_id}/findings",
                      headers=auth(investigator_token)).json()
    assert body["count"] >= 1
    assert body["provenance_legend"]["consistency"] == "deterministic_rule"
    high = client.get(f"/api/documents/{document_id}/findings",
                      params={"severity": "high"},
                      headers=auth(investigator_token)).json()
    assert all(f["severity"] == "high" for f in high["items"])


def test_signed_links_are_minted_and_honoured(client, investigator_token, analysed_document):
    _, document_id = analysed_document
    links = client.post(f"/api/documents/{document_id}/links",
                        headers=auth(investigator_token)).json()
    assert links and any(link["purpose"] == "original" for link in links)
    original = next(link for link in links if link["purpose"] == "original")
    # No Authorization header: the signature alone authorises the fetch.
    streamed = client.get(original["url"].replace("/api", "/api", 1))
    assert streamed.status_code == 200
    assert streamed.headers["content-type"] == "application/pdf"

    page_link = next(link for link in links if link["purpose"].startswith("page_render"))
    render = client.get(page_link["url"])
    assert render.status_code == 200
    assert render.headers["content-type"] == "image/png"


def test_tampered_signature_is_rejected(client, investigator_token, analysed_document):
    _, document_id = analysed_document
    links = client.post(f"/api/documents/{document_id}/links",
                        headers=auth(investigator_token)).json()
    url = next(link["url"] for link in links if link["purpose"] == "original")
    assert client.get(url.replace("sig=", "sig=0")).status_code == 401


def test_page_render_layer_that_does_not_exist_is_reported(client, investigator_token,
                                                           analysed_document):
    _, document_id = analysed_document
    response = client.get(f"/api/documents/{document_id}/pages/1/render",
                          params={"layer": "nonexistent"},
                          headers=auth(investigator_token))
    assert response.status_code == 404
    assert "Available" in response.json()["error"]["message"]


def test_confirming_a_finding_requires_a_reason(client, investigator_token, analysed_document):
    _, document_id = analysed_document
    findings = client.get(f"/api/documents/{document_id}/findings",
                          headers=auth(investigator_token)).json()["items"]
    target = findings[0]["finding_id"]
    without = client.post(f"/api/documents/{document_id}/review",
                          json={"action": "confirm_finding", "finding_id": target},
                          headers=auth(investigator_token))
    assert without.status_code == 422
    assert "written reason" in without.json()["error"]["message"]


def test_review_confirm_then_reassess_changes_the_score(client, investigator_token,
                                                        analysed_document):
    _, document_id = analysed_document
    findings = client.get(f"/api/documents/{document_id}/findings",
                          headers=auth(investigator_token)).json()["items"]
    dismissable = [f for f in findings if f["severity"] in ("high", "medium")]
    before = client.get(f"/api/documents/{document_id}",
                        headers=auth(investigator_token)).json()["risk_score"]

    for finding in dismissable:
        response = client.post(
            f"/api/documents/{document_id}/review",
            json={"action": "dismiss_finding", "finding_id": finding["finding_id"],
                  "reason": "Confirmed directly with the issuing hospital's finance office."},
            headers=auth(investigator_token),
        )
        assert response.status_code == 200, response.text

    reassessed = client.post(f"/api/documents/{document_id}/reassess",
                             headers=auth(investigator_token)).json()
    assert reassessed["risk"]["score"] < before
    assert reassessed["risk"]["dismissed_signals_excluded"] >= len(dismissable)


def test_reviewer_cannot_escalate_but_investigator_can(client, reviewer_token,
                                                       investigator_token, analysed_document):
    _, document_id = analysed_document
    denied = client.post(f"/api/documents/{document_id}/review",
                         json={"action": "escalate_investigation",
                               "reason": "Requires specialist review of the amounts block."},
                         headers=auth(reviewer_token))
    assert denied.status_code == 403

    allowed = client.post(f"/api/documents/{document_id}/review",
                          json={"action": "escalate_investigation",
                                "reason": "Requires specialist review of the amounts block.",
                                "escalate_priority": "high"},
                          headers=auth(investigator_token))
    assert allowed.status_code == 200
    assert allowed.json()["investigation_id"]


def test_claim_approval_is_blocked_while_high_findings_are_unreviewed(
    client, claims_token, tampered_invoice_pdf, make_claim
):
    data, mime = tampered_invoice_pdf
    claim = make_claim()
    upload(client, claims_token, data, "blocked.pdf", mime, claim["id"], analyze=True)
    client.post(f"/api/documents/{claim['documents'][0]['id'] if claim.get('documents') else ''}"
                "/analyze", json={"force": True}, headers=auth(claims_token))
    response = client.post(
        f"/api/claims/{claim['id']}/decision",
        json={"decision": "approve",
              "reason": "Looks acceptable on the face of the paperwork submitted."},
        headers=auth(claims_token),
    )
    assert response.status_code == 409
    assert "unreviewed" in response.json()["error"]["message"]


def test_verification_can_be_run_on_demand(client, investigator_token, analysed_document):
    _, document_id = analysed_document
    response = client.post(f"/api/verification/documents/{document_id}/run",
                           json={"request_types": ["policy_lookup", "invoice_lookup"]},
                           headers=auth(investigator_token))
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results
    for result in results:
        if result.get("skipped"):
            continue
        assert result["is_demo_provider"] is True
        assert result["result"]["is_demo_data"] is True
        assert "DEMO VERIFICATION PROVIDER" in result["result"]["data_source_disclaimer"]


def test_investigation_notes_and_listing(client, investigator_token, analysed_document):
    claim, document_id = analysed_document
    client.post(f"/api/documents/{document_id}/review",
                json={"action": "escalate_investigation",
                      "reason": "Escalating for a second opinion on the overwritten total."},
                headers=auth(investigator_token))
    listing = client.get("/api/investigations", params={"page_size": 50},
                         headers=auth(investigator_token)).json()
    case = next(i for i in listing["items"] if i["claim_id"] == claim["id"])
    note = client.post(f"/api/investigations/{case['id']}/notes",
                       json={"body": "Requested the signed original from the provider."},
                       headers=auth(investigator_token))
    assert note.status_code == 201
    detail = client.get(f"/api/investigations/{case['id']}",
                        headers=auth(investigator_token)).json()
    assert detail["notes"] and detail["notes"][-1]["body"].startswith("Requested")
    assert detail["claim"]["claim_number"] == claim["claim_number"]


def test_report_is_generated_and_downloadable(client, investigator_token, analysed_document):
    _, document_id = analysed_document
    created = client.post("/api/reports", json={"document_id": document_id},
                          headers=auth(investigator_token))
    assert created.status_code == 201, created.text
    report = created.json()
    assert report["file_size"] > 5000
    assert report["sha256"] and report["document_sha256"]
    assert report["pipeline_version"]

    export = client.get(f"/api/reports/{report['id']}/export",
                        headers=auth(investigator_token))
    assert export.status_code == 200
    assert export.content.startswith(b"%PDF")
    assert export.headers["x-report-sha256"] == report["sha256"]


def test_dashboard_aggregates_are_present(client, investigator_token, analysed_document):
    body = client.get("/api/dashboard", headers=auth(investigator_token)).json()
    for key in ("documents_total", "documents_processed", "pending_review", "high_concern",
                "verified", "processing_errors"):
        assert key in body["cards"], key
    assert body["risk_distribution"]
    assert body["findings_by_kind"]
    assert isinstance(body["daily_volume"], list)
    assert "demo providers" in body["verification_note"]


def test_audit_trail_records_the_workflow_and_verifies(client, admin_token, analysed_document):
    _, document_id = analysed_document
    logs = client.get("/api/audit-logs", params={"resource_id": document_id, "page_size": 100},
                      headers=auth(admin_token)).json()
    actions = {entry["action"] for entry in logs["items"]}
    assert {"document.uploaded", "analysis.started", "analysis.completed"} <= actions
    assert all(entry["entry_hash"] for entry in logs["items"])

    chain = client.get("/api/audit-logs/chain/verify", headers=auth(admin_token)).json()
    assert chain["intact"] is True
    assert chain["entries_checked"] > 0
    assert "sha256" in chain["algorithm"]


def test_openapi_document_is_served(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"]
    assert "/api/documents" in schema["paths"]
    assert "/api/claims/{claim_id}/decision" in schema["paths"]
    # The contract states plainly what the platform does not claim.
    assert "does not" in schema["info"]["description"].lower()


def test_capabilities_endpoint_exposes_limits_and_providers(client):
    body = client.get("/api/system/capabilities").json()
    assert body["upload"]["max_size_mb"] > 0
    assert "application/pdf" in body["upload"]["allowed_mime_types"]
    assert body["providers"]["aigc"]["active"]
    assert body["versions"]["pipeline"]

"""Upload validation, malware handling and evidence integrity."""
from __future__ import annotations

import hashlib

from app.services.malware.scanner import EICAR, HeuristicScanner
from app.services.validation import sanitize_filename, sniff_mime, validate_upload
from tests.conftest import auth, upload


def test_executable_is_rejected(client, claims_token):
    response = upload(client, claims_token, b"MZ\x90\x00" + b"\x00" * 900,
                      "payload.exe", "application/octet-stream")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_document"


def test_extension_spoofing_is_caught_by_content_sniffing(client, claims_token):
    response = upload(client, claims_token, b"MZ\x90\x00" + b"\x00" * 900,
                      "invoice.pdf", "application/pdf")
    assert response.status_code == 415


def test_corrupt_pdf_is_rejected(client, claims_token):
    response = upload(client, claims_token, b"%PDF-1.7\n truncated nonsense",
                      "broken.pdf", "application/pdf")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "corrupt_document"


def test_empty_file_is_rejected(client, claims_token):
    response = upload(client, claims_token, b"", "empty.pdf", "application/pdf")
    assert response.status_code == 400


def test_oversized_upload_is_rejected(client, claims_token, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 1)
    payload = b"%PDF-1.7\n" + b"0" * (2 * 1024 * 1024)
    response = upload(client, claims_token, payload, "big.pdf", "application/pdf")
    assert response.status_code in (400, 413)


def test_filename_is_sanitised():
    assert sanitize_filename("../../etc/passwd") == "etc_passwd" or \
        "/" not in sanitize_filename("../../etc/passwd")
    assert "\x00" not in sanitize_filename("bad\x00name.pdf")


def test_mime_sniffing_prefers_content(invoice_pdf):
    data, _ = invoice_pdf
    mime, extension = sniff_mime(data)
    assert mime == "application/pdf" and extension == "pdf"


def test_validation_reports_declared_mime_mismatch(invoice_pdf):
    data, _ = invoice_pdf
    result = validate_upload(data, "invoice.pdf", "image/png")
    assert any("does not match" in warning for warning in result.warnings)


def test_eicar_is_quarantined_and_preserved(client, claims_token, investigator_token,
                                            invoice_pdf, make_claim):
    data, mime = invoice_pdf
    infected = data + b"\n% " + EICAR
    claim = make_claim()
    response = upload(client, claims_token, infected, "infected.pdf", mime, claim["id"])
    assert response.status_code == 201, response.text
    document_id = response.json()["document"]["id"]

    detail = client.get(f"/api/documents/{document_id}",
                        headers=auth(investigator_token)).json()
    assert detail["malware_status"] == "infected"
    assert detail["processing_status"] == "quarantined"
    # The evidence is retained: the stored bytes are still downloadable.
    stream = client.get(f"/api/documents/{document_id}/file",
                        headers=auth(investigator_token))
    assert stream.status_code == 200
    assert stream.headers["x-document-sha256"] == hashlib.sha256(infected).hexdigest()


def test_heuristic_scanner_flags_active_content():
    pdf = b"%PDF-1.7\n<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>\n%%EOF"
    result = HeuristicScanner().scan(pdf, "a.pdf", "application/pdf")
    assert result.status == "suspicious"
    assert any(i["code"] == "pdf_javascript" for i in result.indicators)


def test_sha256_recorded_matches_uploaded_bytes(client, claims_token, invoice_pdf, make_claim):
    data, mime = invoice_pdf
    claim = make_claim()
    body = upload(client, claims_token, data, "invoice.pdf", mime, claim["id"],
                  analyze=False).json()
    assert body["document"]["sha256"] == hashlib.sha256(data).hexdigest()


def test_duplicate_content_is_reported_but_both_copies_kept(
    client, claims_token, investigator_token, invoice_pdf, make_claim
):
    data, mime = invoice_pdf
    first = make_claim()
    second = make_claim()
    a = upload(client, claims_token, data, "one.pdf", mime, first["id"], analyze=False)
    b = upload(client, claims_token, data, "two.pdf", mime, second["id"], analyze=False)
    assert a.status_code == b.status_code == 201
    assert any("identical file" in w for w in b.json()["warnings"])
    assert a.json()["document"]["id"] != b.json()["document"]["id"]


def test_reviewer_cannot_upload(client, reviewer_token, invoice_pdf):
    data, mime = invoice_pdf
    response = upload(client, reviewer_token, data, "invoice.pdf", mime)
    assert response.status_code == 403


def test_unknown_document_returns_404(client, investigator_token):
    response = client.get("/api/documents/00000000-0000-0000-0000-000000000000",
                          headers=auth(investigator_token))
    assert response.status_code == 404

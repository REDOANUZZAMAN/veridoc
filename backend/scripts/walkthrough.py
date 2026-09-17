"""End-to-end walkthrough of the product requirements against a live instance.

Exercises the whole investigator workflow over HTTP - creating a claim, uploading a
generated document with planted anomalies, watching the queue process it, reading
every evidence panel, running verification, adjudicating findings, escalating,
noting, reporting and verifying the audit chain - and asserts the outcome of each
step.

    python scripts/walkthrough.py               # against http://localhost:8088
    API_BASE=https://veridoc.example/api python scripts/walkthrough.py

Requires a seeded instance (the demo accounts and the sample registry) and, when
QUEUE_MODE=redis, a running worker.
"""
import os
import sys
import time

import httpx

BASE = os.environ.get("API_BASE", "http://localhost:8088/api").rstrip("/")
OK, FAIL = "  OK  ", " FAIL "
results = []

def step(n, label, condition, detail=""):
    results.append((n, label, bool(condition)))
    print(f"[{OK if condition else FAIL}] {n:>2}. {label}" + (f"  — {detail}" if detail else ""))
    return condition

client = httpx.Client(timeout=120.0)

# 1. log in
r = client.post(f"{BASE}/auth/login", json={"email": "claims@veridoc.example", "password": "Demo!2026"})
officer = r.json()["access_token"]
OFF = {"Authorization": f"Bearer {officer}"}
r2 = client.post(f"{BASE}/auth/login", json={"email": "investigator@veridoc.example", "password": "Demo!2026"})
inv = r2.json()["access_token"]
INV = {"Authorization": f"Bearer {inv}"}
r3 = client.post(f"{BASE}/auth/login", json={"email": "admin@veridoc.example", "password": "Demo!2026"})
ADM = {"Authorization": f"Bearer {r3.json()['access_token']}"}
step(1, "Log in (claims officer, investigator, admin)", r.status_code == 200 and r2.status_code == 200,
     f"permissions: officer={len(r.json()['user']['permissions'])}, investigator={len(r2.json()['user']['permissions'])}")

# 2. create a claim
claim = client.post(f"{BASE}/claims", headers=OFF, json={
    "customer_name": "Amelia R. Okonkwo", "policy_number": "POL-938472", "claim_type": "health",
    "customer_dob": "1986-04-12", "claimed_amount": "8500.00", "currency": "USD",
    "incident_date": "2026-08-24",
    "summary": "End-to-end walkthrough: day-case procedure claimed at 8,500.00.",
}).json()
step(2, "Create a claim", claim.get("claim_number"), claim.get("claim_number"))

# 3. upload a document (a tampered invoice, generated for this run)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from app.db.demo_documents import DocSpec, render

spec = DocSpec(
    key="journey", kind="pdf", title="Medical Invoice",
    organisation="Meridian General Hospital",
    org_subtitle="Ashford NHS Foundation Trust · Provider registration HRG-114-882",
    party_fields=[("Patient name", "Amelia R. Okonkwo"), ("Date of birth", "1986-04-12"),
                  ("Insured name", "Amelia R. Okonkwo"), ("Policy number", "POL-938472")],
    header_fields=[("Invoice number", "MGH-2026-004918"), ("Invoice date", "2026-08-27"),
                   ("Treatment date", "2026-08-24"), ("Department", "General Surgery"),
                   ("Currency", "USD")],
    items=[("Day-case theatre time (90 min)", "1", "2,400.00", "2,400.00"),
           ("Surgeon fee - laparoscopic procedure", "1", "1,850.00", "1,850.00"),
           ("Anaesthetist fee", "1", "1,250.00", "1,250.00"),
           ("Recovery ward and consumables", "1", "1,000.00", "1,000.00")],
    totals=[("Subtotal", "$6,500.00"), ("Tax", "$0.00"), ("Total amount", "$8,500.00")],
    font_anomaly_field="Total amount", baseline_shift_field="Total amount",
    annotation_overlay=("Total amount", "$8,500.00"),
    producer="Adobe Photoshop 25.3 (Windows)", creator="Microsoft Word",
    footer="Payment due within 30 days.", seed=777,
)
data, ext, mime = render(spec)
upload = client.post(f"{BASE}/documents", headers=OFF,
                     files={"file": ("journey-invoice.pdf", data, mime)},
                     data={"claim_id": claim["id"], "analyze": "true", "source": "portal_upload"})
body = upload.json()
doc_id = body["document"]["id"]
step(3, "Upload a document (validated, hashed, stored)", upload.status_code == 201,
     f"{body['document']['document_ref']} sha256={body['document']['sha256'][:16]}… mode={body['analysis']['mode']}")

# 4. processing status while the worker picks it up
statuses = []
for _ in range(60):
    detail = client.get(f"{BASE}/documents/{doc_id}", headers=INV).json()
    statuses.append(detail["processing_status"])
    if detail["processing_status"] in ("analyzed", "partial", "failed", "quarantined"):
        break
    time.sleep(1)
step(4, "See processing status change", len(set(statuses)) >= 1 and statuses[-1] in ("analyzed", "partial"),
     " → ".join(dict.fromkeys(statuses)))

# 5. analysis ran through every stage
run = detail["latest_run"]
stage_status = {s["key"]: s["status"] for s in run["stages"]}
step(5, "Run analysis (all 14 stages recorded)", len(run["stages"]) == 14 and stage_status["risk"] == "completed",
     f"completed={sum(1 for v in stage_status.values() if v == 'completed')}/14, pipeline {run['pipeline_version']}")

# 6. OCR results
ocr = detail["ocr"]
step(6, "See OCR results", ocr and ocr[0]["word_count"] > 40,
     f"{ocr[0]['provider']} · {ocr[0]['word_count']} words · {ocr[0]['mean_confidence']:.2%}")

# 7. extracted fields
fields = {f["field_key"]: f["value"] for f in detail["extracted_fields"]}
step(7, "See extracted fields", fields.get("total") == "8500.00" and fields.get("invoice_number"),
     f"{len(fields)} fields; total={fields.get('total')} subtotal={fields.get('subtotal')}")

# 8-11. findings by family
findings = client.get(f"{BASE}/documents/{doc_id}/findings", headers=INV).json()["items"]
kinds = {}
for f in findings:
    kinds.setdefault(f["kind"], []).append(f)
step(8, "See forensic findings", kinds.get("forensic"),
     ", ".join(sorted({f["code"] for f in kinds.get("forensic", [])})))
step(9, "See AIGC analysis", kinds.get("aigc"),
     f"{kinds['aigc'][0]['title']} · model {kinds['aigc'][0]['model_version']} · demo={kinds['aigc'][0].get('is_demo_provider')}")
step(10, "See tampering findings", kinds.get("tampering"),
     ", ".join(f"{f['code']} ({f['affected_field']})" for f in kinds.get("tampering", [])))
step(11, "See consistency checks", kinds.get("consistency"),
     ", ".join(sorted({f["code"] for f in kinds.get("consistency", [])})))
consistency_stage = next(s for s in run["stages"] if s["key"] == "consistency")
step(11.5, "Consistency engine reports passed checks too", consistency_stage["detail"]["passed"] > 0,
     f"{consistency_stage['detail']['passed']} passed / {consistency_stage['detail']['failed']} failed")

# 12. cross-document comparison (upload a second document to the same claim)
spec2 = DocSpec(
    key="journey2", kind="pdf", title="Claim Form", organisation="Northbridge Mutual",
    org_subtitle="Health claims - part A: to be completed by the insured",
    party_fields=[("Insured name", "Amelia R. Okonkwo"), ("Patient name", "Amelia R. Okonkwo"),
                  ("Date of birth", "1986-04-12"), ("Policy number", "POL-938472")],
    header_fields=[("Claim number", claim["claim_number"]), ("Hospital", "Meridian General Hospital"),
                   ("Treatment date", "2026-08-24"), ("Currency", "USD")],
    totals=[("Total amount", "$6,500.00")],
    body_paragraphs=["Declaration by the insured: the amount claimed reflects charges incurred."],
    signature_line="Signature of insured", seed=778,
)
data2, _, mime2 = render(spec2)
up2 = client.post(f"{BASE}/documents", headers=OFF, files={"file": ("journey-claim-form.pdf", data2, mime2)},
                  data={"claim_id": claim["id"], "analyze": "true"})
doc2_id = up2.json()["document"]["id"]
for _ in range(60):
    d2 = client.get(f"{BASE}/documents/{doc2_id}", headers=INV).json()
    if d2["processing_status"] in ("analyzed", "partial", "failed"):
        break
    time.sleep(1)
claim_detail = client.get(f"{BASE}/claims/{claim['id']}", headers=INV).json()
mismatches = [c for c in claim_detail["cross_document"]["comparisons"] if not c["agrees"] and not c.get("skipped")]
step(12, "Compare multiple documents in a claim", mismatches,
     "; ".join(f"{m['label']}: {m['value_a']} vs {m['value_b']} ({m['detail']})" for m in mismatches[:2]))

# 13. demo external verification
verify = client.post(f"{BASE}/verification/documents/{doc_id}/run", headers=INV,
                     json={"request_types": ["policy_lookup", "invoice_lookup", "provider_lookup"]}).json()
executed = [v for v in verify["results"] if not v.get("skipped")]
step(13, "Run demo external verification", executed and all(v["result"]["is_demo_data"] for v in executed),
     "; ".join(f"{v['request_type']}={v['result']['outcome']}" for v in executed))

# 14. risk assessment
risk = client.get(f"{BASE}/documents/{doc_id}", headers=INV).json()["risk_assessment"]
step(14, "See the risk assessment", risk and risk["band"] and risk["top_reasons"],
     f"{risk['score']}/100 {risk['band_label']} · {len(risk['signals'])} signals · weights {risk['weights_version']}")

# 15. highlighted evidence
with_region = [f for f in findings if f["region"] and f["page"]]
links = client.post(f"{BASE}/documents/{doc_id}/links", headers=INV).json()
render_link = next(link for link in links if link["purpose"].startswith("page_render"))
render_response = client.get(BASE.replace("/api", "") + render_link["url"])
step(15, "Open highlighted evidence (region + signed page render)",
     with_region and render_response.status_code == 200 and render_response.headers["content-type"] == "image/png",
     f"{len(with_region)} findings carry a page region; render {len(render_response.content)} bytes")

# 16 + 18. review findings: confirm one, dismiss another (reason required)
target = next(f for f in findings if f["severity"] in ("high", "critical"))
no_reason = client.post(f"{BASE}/documents/{doc_id}/review", headers=INV,
                        json={"action": "confirm_finding", "finding_id": target["finding_id"]})
confirm = client.post(f"{BASE}/documents/{doc_id}/review", headers=INV, json={
    "action": "confirm_finding", "finding_id": target["finding_id"],
    "reason": "Confirmed with the hospital finance office that the issued total was 6,500.00.",
})
step(16, "Review findings (reason enforced on confirm)",
     no_reason.status_code == 422 and confirm.status_code == 200,
     f"without reason → {no_reason.status_code}, with reason → {confirm.status_code}")

weak = next((f for f in findings if f["severity"] in ("low", "medium") and f["kind"] != "aigc"), None)
dismissed = None
if weak:
    dismissed = client.post(f"{BASE}/documents/{doc_id}/review", headers=INV, json={
        "action": "dismiss_finding", "finding_id": weak["finding_id"],
        "reason": "Benign: the annotation is the hospital's own payment stamp, verified on two other invoices.",
    })
before_score = risk["score"]
reassessed = client.post(f"{BASE}/documents/{doc_id}/reassess", headers=INV).json()["risk"]
step(18, "Mark findings and have the score respect it",
     reassessed["dismissed_signals_excluded"] >= (1 if weak else 0)
     and any(s["human_confirmed"] for s in reassessed["signals"]),
     f"score {before_score} → {reassessed['score']}, dismissed excluded={reassessed['dismissed_signals_excluded']}")

# 17. investigation notes
escalate = client.post(f"{BASE}/documents/{doc_id}/review", headers=INV, json={
    "action": "escalate_investigation", "escalate_priority": "high",
    "reason": "Issuer records a different total; escalating for a provider-level review.",
}).json()
case_id = escalate["investigation_id"]
note = client.post(f"{BASE}/investigations/{case_id}/notes", headers=INV, json={
    "body": "Requested a signed copy of MGH-2026-004918 from the provider; settlement on hold.",
    "note_type": "evidence_request",
})
case = client.get(f"{BASE}/investigations/{case_id}", headers=INV).json()
step(17, "Add investigation notes", note.status_code == 201 and case["notes"],
     f"{case['case_number']} · {len(case['notes'])} note(s) · status {case['status']}")

# 19. generate a report
report = client.post(f"{BASE}/reports", headers=INV, json={"document_id": doc_id}).json()
pdf = client.get(f"{BASE}/reports/{report['id']}/export", headers=INV)
step(19, "Generate a report (PDF)",
     pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and report["sha256"],
     f"{report['report_ref']} · {len(pdf.content)} bytes · sha256 {report['sha256'][:16]}… · doc hash {report['document_sha256'][:16]}…")

# 20. audit history + chain verification
audit = client.get(f"{BASE}/audit-logs", headers=ADM,
                   params={"resource_id": doc_id, "page_size": 100}).json()
chain = client.get(f"{BASE}/audit-logs/chain/verify", headers=ADM).json()
actions = [e["action"] for e in audit["items"]]
expected = {"document.uploaded", "analysis.started", "analysis.completed", "review.action",
            "verification.requested", "verification.completed", "report.generated"}
step(20, "View the complete audit history (hash chain intact)",
     expected <= set(actions) and chain["intact"],
     f"{audit['meta']['total']} entries for this document; chain intact over {chain['entries_total']}")

# extra: claim decision is blocked while high findings are unreviewed, then allowed
blocked = client.post(f"{BASE}/claims/{claim['id']}/decision", headers=OFF,
                      json={"decision": "approve", "reason": "Looks fine on the paperwork."})
step(21, "Claim approval blocked while high findings are unadjudicated",
     blocked.status_code == 409, blocked.json()["error"]["message"][:110])

referred = client.post(f"{BASE}/claims/{claim['id']}/decision", headers=OFF, json={
    "decision": "refer",
    "reason": "Referred to the provider-network team: the issuer's record of the invoice total differs.",
})
step(22, "Claim decision recorded by a named officer", referred.status_code == 200,
     f"{referred.json()['status']} · decision={referred.json()['decision']}")

print()
passed = sum(1 for _, _, ok in results if ok)
print(f"{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)

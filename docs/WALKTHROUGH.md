# Walkthrough: the twenty requirements, demonstrated

Two ways to verify the product end to end.

## A. Scripted, against a live instance

```bash
cd backend
../.venv/bin/python scripts/walkthrough.py
```

The script signs in as three roles, creates a claim, generates and uploads a document with planted
anomalies, waits for the queue to process it, reads every evidence panel through the API, runs
verification, adjudicates findings, escalates, notes, reports, and verifies the audit chain —
asserting the outcome of each step. Requires a seeded instance and (with `QUEUE_MODE=redis`) a
running worker.

Expected output:

```
[  OK  ]  1. Log in (claims officer, investigator, admin)  — permissions: officer=20, investigator=24
[  OK  ]  2. Create a claim  — CLM-2026-000011
[  OK  ]  3. Upload a document (validated, hashed, stored)  — DOC-2026-000023 sha256=c4db0fb674a50252… mode=redis
[  OK  ]  4. See processing status change  — queued → analyzed
[  OK  ]  5. Run analysis (all 14 stages recorded)  — completed=14/14, pipeline 1.4.0
[  OK  ]  6. See OCR results  — pdf_text · 89 words · 99.50%
[  OK  ]  7. See extracted fields  — 14 fields; total=8500.00 subtotal=6500.00
[  OK  ]  8. See forensic findings  — PDF_CONTENT_ANNOTATIONS, PDF_IMAGE_EDITOR_PRODUCER,
                                     PDF_PRODUCER_CREATOR_MISMATCH, PDF_TEXT_FONT_MIX_IN_LINE
[  OK  ]  9. See AIGC analysis  — No significant synthetic-media indicators detected (page 1)
                                  · model veridoc-demo-heuristic@0.4.0 · demo=True
[  OK  ] 10. See tampering findings  — TAMPER_EDITED_AMOUNT (total), TAMPER_OVERLAY_ANNOTATION
[  OK  ] 11. See consistency checks  — TOTAL_ARITHMETIC_MISMATCH
[  OK  ] 11.5. Consistency engine reports passed checks too  — 11 passed / 1 failed
[  OK  ] 12. Compare multiple documents in a claim  — Total amount: 8500.00 vs 6500.00 (differ by 2000.00)
[  OK  ] 13. Run demo external verification  — policy_lookup=match; invoice_lookup=mismatch; provider_lookup=match
[  OK  ] 14. See the risk assessment  — 100/100 High Concern · 8 signals · weights 2026.09.1
[  OK  ] 15. Open highlighted evidence (region + signed page render)  — 4 findings carry a page region
[  OK  ] 16. Review findings (reason enforced on confirm)  — without reason → 422, with reason → 200
[  OK  ] 18. Mark findings and have the score respect it  — dismissed excluded=1
[  OK  ] 17. Add investigation notes  — INV-2026-000011 · 1 note(s) · status escalated
[  OK  ] 19. Generate a report (PDF)  — RPT-2026-000001 · 24475 bytes · sha256 6da09c5f… · doc hash c6f2d92b…
[  OK  ] 20. View the complete audit history (hash chain intact)  — 22 entries; chain intact over 125
[  OK  ] 21. Claim approval blocked while high findings are unadjudicated
[  OK  ] 22. Claim decision recorded by a named officer  — resolved · decision=refer

23/23 checks passed
```

## B. By hand, in the console

Sign in at <http://localhost:3010> as `investigator@veridoc.example` / `Demo!2026`.

| # | Requirement | Where |
|---|---|---|
| 1 | **Log in** | Sign-in page. The demo panel switches between the four roles; note how the sidebar and the action bar change with the role's permissions |
| 2 | **Create a claim** | *Claims → New claim* (as `claims@veridoc.example`). The claim particulars are what documents are later checked against |
| 3 | **Upload a document** | *Documents → Upload document*, or from a claim. Drag-and-drop, per-file progress, and the response shows the reference, the SHA-256 taken at ingest, and any warnings |
| 4 | **See processing status** | The Documents table shows `Queued → Processing → Analysed`; the document page shows the same as a stage timeline |
| 5 | **Run analysis** | Automatic on upload. *Re-run analysis* on the document page re-queues it; human decisions are preserved |
| 6 | **See OCR results** | *Extracted data → Recognition detail* — provider, version, word count, mean confidence, duration, and the raw recognised text per page |
| 7 | **See extracted fields** | *Extracted data* — every field with its value, type, confidence, source and page. Click the page button to box it on the document |
| 8 | **See forensic findings** | *Forensics* — findings plus the full metadata table with anomalous rows flagged, and the raw measurements including metrics that did not fire |
| 9 | **See AIGC analysis** | *AIGC analysis* — band, likelihood, provider, model name and version, all eight indicator contributions, and the demo disclaimer |
| 10 | **See tampering findings** | *Tampering* — which independent detectors agreed, on what area, and which extracted field the region covers |
| 11 | **See consistency checks** | *Consistency* — failed rules *and* passed ones, with severity, weight and the rule code; toggle to see rules that did not apply |
| 12 | **Compare multiple documents** | *Cross-document* on the document, or the *Cross-document* tab on the claim for the full matrix, including fields deliberately not compared and why |
| 13 | **Run demo external verification** | *Verification → Run checks now*. Every answer is labelled as demo data with its disclaimer |
| 14 | **See the risk assessment** | *Overview* — band, score, meter, plain-language explanation, per-signal contributions, the published formula, and the interpretation note |
| 15 | **Open highlighted evidence** | Click *Show* on any risk contributor, or the page button on a finding. The viewer jumps to the page and boxes the region; zoom, rotate, page through, switch to a forensic layer, download the original |
| 16 | **Review findings** | *Confirm* / *Dismiss* on any finding. Try submitting without a reason — the server refuses |
| 17 | **Add investigation notes** | *Escalate* on the document, then open the case from *Investigations* and add a typed note |
| 18 | **Mark findings** | Dismiss a finding, then press *Recompute risk*: the score drops and the response states how many dismissed signals were excluded |
| 19 | **Generate a report** | *Generate report* on the document, then open the PDF from *Reports* |
| 20 | **View the audit history** | *Audit trail* on the document, or *Audit Logs* for everything — with the hash chain verified at the top of the page |

## What the PDF report contains

1. Cover — band, score, explanation, interpretation note
2. Document information — reference, filename, detected type and confidence, size, **SHA-256**, intake source, security scan, processing status, human verification state
3. Claim information
4. Processing information — run id, pipeline/rules/weights versions, execution mode, duration, provider snapshot, and the full stage table
5. Extracted information — every field with type, confidence and page; line items
6. Findings by family, each tagged `[MEASURED]` / `[RULE]` / `[MODEL]` / `[HUMAN]`, with confidence, status, page, detector and model version, and any reviewer reason
7. Synthetic-media detail — provider, model, version, whether it is a demo provider, and its disclaimer
8. Trusted-source verification — every check with expected vs actual, marked `[EXTERNAL - DEMO]` where the answer came from the bundled registry
9. Risk composition — every signal with weight, confidence and contribution, plus the formula and a coverage note if any stage degraded
10. Human review actions — who, when, what, why
11. Audit trail extract with the chain state
12. Standing limitations

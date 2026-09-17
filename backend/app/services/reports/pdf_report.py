"""Investigation report generator (PDF).

The report is evidential, so it is explicit about provenance. Every finding is
tagged with how it was produced:

    [MODEL]    probabilistic model inference (synthetic-media analysis)
    [MEASURED] deterministic forensic measurement
    [RULE]     deterministic rule evaluation
    [EXTERNAL] trusted-source verification (demo or production, stated)
    [HUMAN]    a named reviewer's decision

It also prints the document SHA-256, pipeline version, rules version and model
versions, so any conclusion can be traced to the exact code and data that
produced it.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import PIPELINE_VERSION, RISK_WEIGHTS_VERSION, RULES_VERSION
from app.db.enums import RISK_BAND_LABELS

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
RULE = colors.HexColor("#cbd5e1")
BAND_COLOURS = {
    "low_concern": colors.HexColor("#0f766e"),
    "review_recommended": colors.HexColor("#b45309"),
    "high_concern": colors.HexColor("#b91c1c"),
}
SEVERITY_COLOURS = {
    "critical": colors.HexColor("#7f1d1d"), "high": colors.HexColor("#b91c1c"),
    "medium": colors.HexColor("#b45309"), "low": colors.HexColor("#0369a1"),
    "info": colors.HexColor("#475569"),
}
PROVENANCE_TAGS = {
    "model_inference": "[MODEL]",
    "automated_measurement": "[MEASURED]",
    "automated_correlation": "[MEASURED]",
    "deterministic_rule": "[RULE]",
}

STANDING_DISCLAIMER = (
    "This report is decision support for a human investigator. It does not determine whether a "
    "document is genuine or fraudulent. Forensic and synthetic-media signals are probabilistic "
    "indicators with legitimate alternative explanations; rule findings are deterministic but "
    "depend on extraction accuracy; external verification results are only as authoritative as "
    "the source that answered. No claim decision may be made on the basis of this report alone."
)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=20, textColor=INK, spaceAfter=2),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=9.5, textColor=MUTED,
                                   spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Helvetica-Bold",
                             fontSize=13, textColor=INK, spaceBefore=14, spaceAfter=5),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=10.5, textColor=INK, spaceBefore=9, spaceAfter=3),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9, leading=12.6,
                               textColor=INK, alignment=TA_LEFT),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=7.8, leading=10.5,
                                textColor=MUTED),
        "mono": ParagraphStyle("m", parent=base["Normal"], fontName="Courier", fontSize=7.6,
                               leading=9.8, textColor=INK),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8, leading=10.5,
                               textColor=INK),
        "cellsm": ParagraphStyle("cs", parent=base["Normal"], fontSize=7.4, leading=9.4,
                                 textColor=INK),
    }


def _kv_table(rows: list[tuple[str, Any]], styles, width=170 * mm) -> Table:
    def cell(value: Any):
        # Callers may pass a pre-built flowable (e.g. a monospaced hash); only
        # plain values get wrapped, otherwise the flowable would be stringified.
        if isinstance(value, Flowable):
            return value
        return Paragraph("" if value is None else str(value), styles["cell"])

    data = [[Paragraph(f"<b>{k}</b>", styles["cell"]), cell(v)] for k, v in rows]
    table = Table(data, colWidths=[52 * mm, width - 52 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return table


def _grid_table(header: list[str], rows: list[list[Any]], styles, widths: list[float]) -> Table:
    data = [[Paragraph(f"<b>{h}</b>", styles["cellsm"]) for h in header]]
    for row in rows:
        data.append([
            cell if isinstance(cell, Paragraph)
            else Paragraph("" if cell is None else str(cell), styles["cellsm"])
            for cell in row
        ])
    table = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 11 * mm,
                      f"VeriDoc investigation report - {doc.veridoc_ref} - "
                      f"pipeline {PIPELINE_VERSION} / rules {RULES_VERSION}")
    canvas.drawRightString(190 * mm, 11 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_report(payload: dict) -> bytes:
    """``payload`` is assembled by the reports route (see routes/reports.py)."""
    styles = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title=payload.get("title", "Document Investigation Report"),
        author="VeriDoc", subject="Insurance document authenticity assessment",
    )
    document.veridoc_ref = payload.get("report_ref", "-")
    story: list = []
    doc = payload.get("document") or {}
    claim = payload.get("claim") or {}
    risk = payload.get("risk") or {}
    findings = payload.get("findings") or []

    # ----------------------------------------------------------------- header
    story.append(Paragraph(payload.get("title", "Document Investigation Report"),
                           styles["title"]))
    story.append(Paragraph(
        f"Report {payload.get('report_ref')} &nbsp;•&nbsp; generated "
        f"{payload.get('generated_at')} by {payload.get('generated_by', 'system')} "
        f"({payload.get('generated_by_role', '-')})",
        styles["subtitle"],
    ))

    band = risk.get("band") or "low_concern"
    colour = BAND_COLOURS.get(band, MUTED)
    summary_table = Table(
        [[Paragraph(f'<font color="{colour.hexval()}"><b>'
                    f'{RISK_BAND_LABELS.get(band, band).upper()}</b></font>', styles["h1"]),
          Paragraph(f'<font size="17"><b>{risk.get("score", "-")}</b></font>'
                    f'<font size="9" color="{MUTED.hexval()}"> / 100 risk score</font>',
                    styles["body"])]],
        colWidths=[105 * mm, 65 * mm], hAlign="LEFT",
    )
    summary_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colour),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(risk.get("explanation", "No risk assessment is available."),
                           styles["body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<i>{risk.get('interpretation_note', '')}</i>", styles["small"]))

    # -------------------------------------------------------- document / claim
    story.append(Paragraph("1. Document information", styles["h1"]))
    story.append(_kv_table([
        ("Document reference", doc.get("document_ref")),
        ("Original filename", doc.get("original_filename")),
        ("Detected type", f"{doc.get('classification_label') or doc.get('classification_type')} "
                          f"({(doc.get('classification_confidence') or 0) * 100:.0f}% confidence)"),
        ("Content type / size", f"{doc.get('mime_type')} · {doc.get('file_size', 0):,} bytes · "
                                f"{doc.get('page_count')} page(s)"),
        ("SHA-256", Paragraph(f"<font face='Courier' size='7.4'>{doc.get('sha256')}</font>",
                              styles["cell"])),
        ("Uploaded", f"{doc.get('uploaded_at')} by "
                     f"{(doc.get('uploaded_by') or {}).get('email', 'unknown')}"),
        ("Intake source", doc.get("source")),
        ("Security scan", f"{doc.get('malware_status')} — "
                          f"{(doc.get('malware_detail') or {}).get('scanner', '-')}"),
        ("Processing status", f"{doc.get('processing_status')} — {doc.get('processing_message')}"),
        ("Human verification state", doc.get("verification_state")),
    ], styles))

    if claim:
        story.append(Paragraph("2. Claim information", styles["h1"]))
        story.append(_kv_table([
            ("Claim number", claim.get("claim_number")),
            ("Customer", claim.get("customer_name")),
            ("Policy number", claim.get("policy_number")),
            ("Insurer / type", f"{claim.get('insurer')} · {claim.get('claim_type')}"),
            ("Claimed amount", f"{claim.get('claimed_amount')} {claim.get('currency')}"),
            ("Incident date", claim.get("incident_date")),
            ("Claim status", claim.get("status")),
            ("Assigned investigator",
             (claim.get("assigned_investigator") or {}).get("full_name", "unassigned")),
            ("Claim risk", f"{claim.get('risk_score')}/100 "
                           f"({RISK_BAND_LABELS.get(claim.get('risk_band') or '', '-')})"),
        ], styles))

    # ----------------------------------------------------------- processing log
    story.append(Paragraph("3. Processing information", styles["h1"]))
    run = payload.get("run") or {}
    story.append(_kv_table([
        ("Analysis run", run.get("id")),
        ("Pipeline version", run.get("pipeline_version", PIPELINE_VERSION)),
        ("Rules version", run.get("rules_version", RULES_VERSION)),
        ("Risk weights version", risk.get("weights_version", RISK_WEIGHTS_VERSION)),
        ("Execution mode", run.get("queue_mode")),
        ("Started / finished", f"{run.get('started_at')} → {run.get('finished_at')}"),
        ("Duration", f"{(run.get('duration_ms') or 0) / 1000:.1f} s"),
        ("Providers", ", ".join(
            f"{k}: {(v or {}).get('label') or (v or {}).get('key') or '-'}"
            for k, v in (run.get("provider_snapshot") or {}).items()
            if isinstance(v, dict)
        ) or "-"),
    ], styles))
    stages = run.get("stages") or []
    if stages:
        story.append(Spacer(1, 4))
        story.append(_grid_table(
            ["Stage", "Status", "ms", "Findings", "Detail"],
            [[s.get("label"), s.get("status"), s.get("duration_ms"), s.get("findings"),
              (s.get("message") or "")[:190]] for s in stages],
            styles, [40 * mm, 22 * mm, 13 * mm, 16 * mm, 79 * mm],
        ))

    # ------------------------------------------------------------- extraction
    story.append(PageBreak())
    story.append(Paragraph("4. Extracted information", styles["h1"]))
    fields = payload.get("extracted_fields") or []
    if fields:
        story.append(_grid_table(
            ["Field", "Value", "Type", "Conf.", "Page"],
            [[f.get("field_label"), (f.get("value") or f.get("value_raw") or "")[:90],
              f.get("value_type"), f"{(f.get('confidence') or 0) * 100:.0f}%", f.get("page")]
             for f in fields],
            styles, [44 * mm, 72 * mm, 20 * mm, 16 * mm, 18 * mm],
        ))
    else:
        story.append(Paragraph("No fields were extracted from this document.", styles["body"]))
    items = payload.get("line_items") or []
    if items:
        story.append(Paragraph("Line items", styles["h2"]))
        story.append(_grid_table(
            ["#", "Extracted row", "Page"],
            [[i + 1, (it.get("raw") or it.get("value") or "")[:130], it.get("page")]
             for i, it in enumerate(items)],
            styles, [10 * mm, 140 * mm, 20 * mm],
        ))

    # --------------------------------------------------------------- findings
    story.append(Paragraph("5. Findings", styles["h1"]))
    story.append(Paragraph(
        "Provenance tags: <b>[MEASURED]</b> deterministic forensic measurement · "
        "<b>[RULE]</b> deterministic rule · <b>[MODEL]</b> probabilistic model inference · "
        "<b>[EXTERNAL]</b> trusted-source verification · <b>[HUMAN]</b> reviewer decision.",
        styles["small"],
    ))
    story.append(Spacer(1, 4))
    if findings:
        for group_label, kinds in (
            ("5.1 Forensic and metadata findings", {"forensic"}),
            ("5.2 Synthetic-media (AIGC) analysis", {"aigc"}),
            ("5.3 Tampering indicators", {"tampering"}),
            ("5.4 Internal consistency", {"consistency"}),
            ("5.5 Cross-document comparison", {"cross_document"}),
        ):
            subset = [f for f in findings if f.get("kind") in kinds]
            if not subset:
                continue
            story.append(Paragraph(group_label, styles["h2"]))
            rows = []
            for f in subset:
                tag = PROVENANCE_TAGS.get(f.get("provenance", ""), "[MEASURED]")
                if f.get("status") in {"confirmed", "dismissed"}:
                    tag += " [HUMAN]"
                sev = SEVERITY_COLOURS.get(f.get("severity"), MUTED)
                rows.append([
                    Paragraph(f"<font color='{sev.hexval()}'><b>{f.get('severity', '').upper()}"
                              f"</b></font><br/><font size='6.6'>{tag}</font>", styles["cellsm"]),
                    Paragraph(f"<b>{f.get('title', '')}</b><br/>{f.get('description', '')[:520]}"
                              + (f"<br/><i>Reviewer: {f.get('review_reason')}</i>"
                                 if f.get("review_reason") else ""),
                              styles["cellsm"]),
                    Paragraph(f"{(f.get('confidence') or 0) * 100:.0f}%<br/>"
                              f"<font size='6.6'>{f.get('status')}</font>", styles["cellsm"]),
                    Paragraph(f"p{f.get('page') or '-'}<br/><font size='6.4'>"
                              f"{f.get('detector', '')}<br/>{f.get('model_version', '')}</font>",
                              styles["cellsm"]),
                ])
            story.append(_grid_table(
                ["Severity", "Finding", "Conf.", "Locus / detector"], rows, styles,
                [22 * mm, 100 * mm, 18 * mm, 30 * mm],
            ))
    else:
        story.append(Paragraph(
            "No findings were raised by the stages that completed. Note that an absence of "
            "findings is not a certificate of authenticity - see the coverage note below.",
            styles["body"],
        ))

    # ------------------------------------------------------------------- AIGC
    aigc = payload.get("aigc_summary") or {}
    if aigc:
        story.append(Paragraph("6. Synthetic-media analysis detail", styles["h1"]))
        story.append(_kv_table([
            ("Provider", aigc.get("provider_label")),
            ("Model / version", f"{aigc.get('model_name')} @ {aigc.get('model_version')}"),
            ("Demo provider", "YES - results are heuristic, not model-calibrated"
                              if aigc.get("is_demo") else "no"),
            ("Highest page likelihood", f"{(aigc.get('max_likelihood') or 0):.2f} "
                                        f"({aigc.get('band_label')})"),
        ], styles))
        if aigc.get("disclaimer"):
            story.append(Spacer(1, 3))
            story.append(Paragraph(f"<i>{aigc['disclaimer']}</i>", styles["small"]))

    # ----------------------------------------------------------- verification
    verifications = payload.get("verification") or []
    story.append(Paragraph("7. Trusted-source verification", styles["h1"]))
    if verifications:
        rows = []
        for v in verifications:
            result = v.get("result") or {}
            checks = result.get("checks") or []
            detail = "<br/>".join(
                f"{'PASS' if c.get('passed') else ('FAIL' if c.get('passed') is False else 'N/A')}"
                f" — {c.get('label')}: expected {c.get('expected')}, got {c.get('actual')}"
                for c in checks[:6]
            ) or "—"
            rows.append([
                Paragraph(f"<b>{v.get('request_type')}</b><br/><font size='6.6'>"
                          f"{v.get('provider_label')}"
                          f"{' · DEMO DATA' if result.get('is_demo_data') else ''}</font>",
                          styles["cellsm"]),
                Paragraph(f"<b>{(result.get('outcome') or 'n/a').upper()}</b><br/>"
                          f"{(result.get('summary') or '')[:260]}", styles["cellsm"]),
                Paragraph(detail, styles["cellsm"]),
            ])
        story.append(_grid_table(["Check", "Outcome", "Detail"], rows, styles,
                                 [36 * mm, 62 * mm, 72 * mm]))
        if any((v.get("result") or {}).get("is_demo_data") for v in verifications):
            story.append(Spacer(1, 3))
            story.append(Paragraph(
                "<b>[EXTERNAL - DEMO]</b> One or more results above came from the bundled demo "
                "registry. No external insurer, hospital, government or banking system was "
                "contacted. These are not real-world confirmations.", styles["small"],
            ))
    else:
        story.append(Paragraph("No trusted-source verification was performed on this document.",
                               styles["body"]))

    # ------------------------------------------------------- risk composition
    story.append(Paragraph("8. Risk assessment composition", styles["h1"]))
    if risk.get("signals"):
        story.append(_grid_table(
            ["Signal", "Category", "Sev.", "Conf.", "Weight", "Contribution"],
            [[s.get("label", "")[:70], s.get("category_label", s.get("category")),
              s.get("severity"), f"{(s.get('confidence') or 0):.2f}", s.get("weight"),
              s.get("contribution")]
             for s in risk["signals"]],
            styles, [58 * mm, 34 * mm, 16 * mm, 14 * mm, 16 * mm, 24 * mm],
        ))
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"<font face='Courier' size='7'>{risk.get('formula', '')}</font>",
                               styles["small"]))
    coverage = risk.get("coverage") or {}
    if coverage.get("degraded_stages"):
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            f"<b>Coverage note:</b> {len(coverage['degraded_stages'])} stage(s) did not complete "
            f"({', '.join(coverage['degraded_stages'])}). Findings from those areas are absent "
            "from this assessment by omission, not by exclusion.", styles["small"],
        ))

    # -------------------------------------------------------- reviewer actions
    story.append(Paragraph("9. Human review actions", styles["h1"]))
    reviews = payload.get("review_actions") or []
    if reviews:
        story.append(_grid_table(
            ["When", "Actor", "Action", "Reason"],
            [[str(r.get("created_at"))[:19], (r.get("actor") or {}).get("email", "-"),
              r.get("action"), (r.get("reason") or "")[:170]] for r in reviews],
            styles, [30 * mm, 42 * mm, 34 * mm, 64 * mm],
        ))
    else:
        story.append(Paragraph(
            "No human review action has been recorded for this document yet. Machine findings "
            "remain unadjudicated.", styles["body"]))

    # ------------------------------------------------------------ audit trail
    story.append(Paragraph("10. Audit trail (most recent entries)", styles["h1"]))
    audit_rows = payload.get("audit") or []
    if audit_rows:
        story.append(_grid_table(
            ["Seq", "When", "Actor", "Action", "Summary"],
            [[a.get("seq"), str(a.get("created_at"))[:19], a.get("actor_email") or "system",
              a.get("action"), (a.get("summary") or "")[:150]] for a in audit_rows],
            styles, [12 * mm, 30 * mm, 40 * mm, 34 * mm, 54 * mm],
        ))
        story.append(Spacer(1, 3))
        chain = payload.get("audit_chain") or {}
        story.append(Paragraph(
            f"Audit chain: {chain.get('entries_total', '?')} entries, integrity "
            f"{'VERIFIED' if chain.get('intact') else 'BROKEN'} "
            f"(sha256 chain, head {str(chain.get('head_hash', ''))[:16]}…).", styles["small"]))

    story.append(Spacer(1, 10))
    story.append(KeepTogether([
        Paragraph("Standing limitations", styles["h2"]),
        Paragraph(STANDING_DISCLAIMER, styles["small"]),
        Spacer(1, 4),
        Paragraph(
            f"Document hash (SHA-256): <font face='Courier'>{doc.get('sha256')}</font><br/>"
            f"Report hash is recorded in the reports register on generation.<br/>"
            f"Pipeline {run.get('pipeline_version', PIPELINE_VERSION)} · "
            f"rules {run.get('rules_version', RULES_VERSION)} · "
            f"risk weights {risk.get('weights_version', RISK_WEIGHTS_VERSION)} · "
            f"generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            styles["small"]),
    ]))

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()

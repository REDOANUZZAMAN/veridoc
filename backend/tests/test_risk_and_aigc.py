"""Risk engine behaviour and synthetic-media analysis guarantees."""
from __future__ import annotations

import pytest

from app.services.aigc.base import BAND_LABELS, AigcTarget, band_for
from app.services.aigc.factory import get_aigc_provider, list_aigc_providers
from app.services.aigc.heuristic_demo import DemoHeuristicAigcProvider
from app.services.risk import engine as R


def finding(code, category, severity="medium", confidence=0.8, status="open", title=None):
    return R.FindingInput(code=code, category=category, severity=severity,
                          confidence=confidence, title=title or code, kind=category,
                          finding_id=f"f-{code}", status=status)


def test_no_signals_gives_low_concern_with_an_explanation():
    result = R.assess([])
    assert result.score == 0
    assert result.band == "low_concern"
    assert "No contributing signals" in result.explanation


def test_score_is_monotone_in_the_number_of_signals():
    one = R.assess([finding("A", "consistency")])
    two = R.assess([finding("A", "consistency"), finding("B", "tampering")])
    three = R.assess([finding("A", "consistency"), finding("B", "tampering"),
                      finding("C", "forensics")])
    assert one.score < two.score < three.score


def test_severity_increases_the_contribution():
    low = R.assess([finding("A", "consistency", severity="low")])
    high = R.assess([finding("A", "consistency", severity="high")])
    assert high.score > low.score


def test_category_saturation_limits_a_crowd_of_weak_signals():
    many = R.assess([finding(f"M{i}", "metadata", severity="low", confidence=0.5)
                     for i in range(20)])
    one_decisive = R.assess([finding("V", "verification", severity="high", confidence=0.91)])
    assert many.category_scores["metadata"]["saturated_score"] <= R.CATEGORY_CAPS["metadata"]
    assert one_decisive.score > many.score


def test_dismissed_findings_are_excluded_and_reported():
    with_open = R.assess([finding("A", "tampering", severity="high")])
    dismissed = R.assess([finding("A", "tampering", severity="high", status="dismissed")])
    assert dismissed.score == 0
    assert dismissed.dismissed_count == 1
    assert "dismissed by a reviewer were excluded" in dismissed.explanation
    assert with_open.score > 0


def test_confirmed_findings_are_treated_as_established():
    open_finding = R.assess([finding("A", "tampering", confidence=0.6)])
    confirmed = R.assess([finding("A", "tampering", confidence=0.6, status="confirmed")])
    assert confirmed.score > open_finding.score
    assert confirmed.signals[0].human_confirmed is True
    assert confirmed.signals[0].source == "human_confirmed_finding"


def test_verification_mismatch_contributes_as_a_signal():
    result = R.assess([], [R.VerificationInput(
        provider_key="demo_policy", provider_label="Demo Policy Registry",
        request_type="policy_lookup", outcome="mismatch", summary="",
        failed_checks=["Policy active"], is_demo_data=True)])
    assert result.score > 0
    assert result.signals[0].category == "verification"
    assert result.signals[0].source == "demo_verification"


def test_matching_verification_is_recorded_as_a_mitigation_not_a_reduction_of_severe_findings():
    match = R.VerificationInput(provider_key="demo_policy", provider_label="P",
                                request_type="policy_lookup", outcome="match", summary="")
    clean = R.assess([], [match])
    with_severe = R.assess([finding("T", "tampering", severity="high")], [match])
    assert clean.mitigations and clean.mitigations[0]["applied"] is False or clean.score == 0
    suppressed = with_severe.mitigations[0]
    assert suppressed["applied"] is False
    assert "high or critical finding" in suppressed["suppressed_reason"]


def test_bands_follow_configured_thresholds():
    assert R.band_for_score(10) == "low_concern"
    assert R.band_for_score(50) == "review_recommended"
    assert R.band_for_score(90) == "high_concern"
    custom = {"review_recommended": 20, "high_concern": 40}
    assert R.band_for_score(25, custom) == "review_recommended"
    assert R.band_for_score(45, custom) == "high_concern"


def test_rule_weights_override_defaults():
    default = R.assess([finding("CODE_X", "consistency")])
    heavier = R.assess([finding("CODE_X", "consistency")], rule_weights={"CODE_X": 40.0})
    assert heavier.score > default.score
    assert heavier.signals[0].weight == 40.0


def test_result_never_describes_the_score_as_a_probability_of_fraud():
    result = R.assess([finding("A", "tampering", severity="critical", confidence=0.99)])
    payload = result.as_dict()
    text = " ".join(str(v) for v in payload.values()).lower()
    for phrase in ("probability of fraud", "definitely fake", "100% fake", "proven fraud"):
        assert phrase not in text
    assert "not a probability that fraud occurred" in payload["interpretation_note"]
    assert payload["band_label"] in ("Low Concern", "Review Recommended", "High Concern")


def test_degraded_coverage_is_disclosed_in_the_explanation():
    result = R.assess([finding("A", "consistency")],
                      stage_coverage={"degraded_stages": ["Image & PDF forensics"]})
    assert "partial coverage" in result.explanation
    assert "absence of findings" in result.explanation


def test_formula_is_published_with_the_result():
    payload = R.assess([finding("A", "consistency")]).as_dict()
    assert "weight x confidence x severity_multiplier" in payload["formula"]
    assert payload["thresholds"]["high_concern"] == R.DEFAULT_THRESHOLDS["high_concern"]


# --------------------------------------------------------------------- AIGC
def test_bands_are_worded_probabilistically():
    for label in BAND_LABELS.values():
        assert "definitely" not in label.lower()
        assert "100%" not in label
    assert band_for(0.1) == "no_significant_indicators"
    assert band_for(0.55) == "possible_indicators"
    assert band_for(0.9) == "notable_indicators"


def test_demo_provider_declares_itself_and_its_model_version():
    described = DemoHeuristicAigcProvider().describe()
    assert described["is_demo"] is True
    assert described["model_name"] == "veridoc-demo-heuristic"
    assert described["model_version"]
    assert "not a trained" in described["disclaimer"]


def test_provider_registry_exposes_a_production_seam():
    keys = {p["key"] for p in list_aigc_providers()}
    assert {"demo_heuristic", "remote_http"} == keys


def test_unavailable_remote_provider_falls_back_and_stays_labelled(monkeypatch):
    monkeypatch.setattr("app.services.aigc.factory._from_db", lambda: "remote_http")
    provider = get_aigc_provider()
    assert provider.is_demo is True  # never silently reports as a production model


def test_analysis_is_deterministic_and_explainable(invoice_pdf):
    from app.services.render import render_document
    from app.services.storage.factory import get_storage

    data, mime = invoice_pdf
    pages = render_document(data, mime, "tests/aigc", get_storage())
    provider = DemoHeuristicAigcProvider()
    target = AigcTarget(page_number=1, image_bytes=pages[0].png_bytes,
                        is_lossless_render=True, ocr_confidences=[0.95] * 30,
                        glyph_heights=[20.0] * 30)
    first = provider.analyze(target)
    second = provider.analyze(target)
    assert first.likelihood == second.likelihood
    assert 0.0 <= first.likelihood <= 0.97
    assert sum(i.weight for i in first.indicators) == pytest.approx(1.0, abs=1e-6)
    payload = first.as_dict()
    assert payload["provider"]["is_demo"] is True
    assert "probabilistic" in payload["uncertainty_note"]
    assert payload["evidence"]["measurements"]


def test_clean_render_yields_no_significant_indicators(invoice_pdf):
    from app.services.render import render_document
    from app.services.storage.factory import get_storage

    data, mime = invoice_pdf
    pages = render_document(data, mime, "tests/aigc2", get_storage())
    result = DemoHeuristicAigcProvider().analyze(AigcTarget(
        page_number=1, image_bytes=pages[0].png_bytes, is_lossless_render=True,
        ocr_confidences=[0.99] * 40, glyph_heights=[19.0] * 40))
    assert result.band == "no_significant_indicators"
    assert "not a certificate of authenticity" in result.summary

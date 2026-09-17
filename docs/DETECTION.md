# Detector catalogue

Every detector below measures something real about the file. This document states, for each one,
**what it measures**, **what it cannot tell you**, and the **benign explanations** an investigator
should rule out — because a detector whose limitations are undocumented is a detector that will be
over-trusted.

Confidence values are calibrated per detector against the measurement itself. They are not
probabilities of fraud.

---

## 1. PDF structure and metadata — `pdf-structure-forensics` 1.5.0

| Finding | Measures | Cannot tell you | Benign causes |
|---|---|---|---|
| `PDF_MODDATE_BEFORE_CREATION` | `/ModDate` earlier than `/CreationDate` | Who changed it, or what changed | A misconfigured clock on the producing system |
| `PDF_EDITED_AFTER_CREATION` | Days between creation and last save | Whether content changed | Legitimate re-issue, re-print, or a signature being added |
| `PDF_IMAGE_EDITOR_PRODUCER` | `/Producer` or `/Creator` names a raster/design editor | That pixels were altered | Cropping, rotating or downscaling a scan in an editor |
| `PDF_MANIPULATION_TOOLING` | Merge/split/re-save tooling named | Anything about content | Most document pipelines use these tools routinely |
| `PDF_PRODUCER_CREATOR_MISMATCH` | Creator and Producer in different software families | Whether the second tool changed anything | Export from one tool, post-process in another |
| `PDF_INCREMENTAL_UPDATE` | Cross-reference generations (`%%EOF`, `startxref`, `/Prev`) | What the appended revision changed | Digital signatures and form filling append revisions by design |
| `PDF_TRAILING_DATA` | Bytes after the final `%%EOF` | What they contain | Some writers pad; some transports append |
| `PDF_CONTENT_ANNOTATIONS` | FreeText/Stamp/Redact/Ink annotations overlaying the page | Whether the annotation contradicts the body | Reviewer comments, approval stamps, legitimate redaction |
| `PDF_MIXED_FONT_EMBEDDING` | Some text uses embedded fonts, some system fonts | Which text was added | Forms with system-font field values |
| `PDF_TEXT_FONT_MIX_IN_LINE` | **Exact**: characters on one line drawn from different font resources | Who set them, or when | A template that bolds or emphasises a single value |
| `PDF_FONT_DIVERSITY` | Distinct typefaces on one page | Anything on its own | Rich templates legitimately use several fonts |
| `PDF_MIXED_IMAGE_COMPRESSION` | Embedded rasters using different codecs | Which one was added | A logo (lossless) beside a photograph (JPEG) |
| `PDF_MASKED_IMAGE_OVERLAY` | Small images carrying a soft mask | Whether the overlay is authorised | Signatures and stamps are placed exactly this way |
| `PDF_EMBEDDED_JAVASCRIPT` / `PDF_EMBEDDED_FILES` | Active content and attachments | Intent | Interactive forms; attached supporting material |

## 2. Image metadata — `image-metadata-forensics` 1.2.0

| Finding | Measures | Benign causes |
|---|---|---|
| `IMG_EDITOR_SOFTWARE_TAG` | EXIF `Software` names an editor | Resizing, cropping or auto-enhancing a photo |
| `IMG_EXIF_TIMESTAMP_DRIFT` | `DateTime` well after `DateTimeOriginal` | Re-saving to compress before upload |
| `IMG_EXIF_FUTURE_TIMESTAMP` | Capture time later than now | Device clock not set |
| `IMG_EXIF_STRIPPED` | No EXIF on a photographic format | Screenshots, exports, and every major messaging app |

## 3. Image forensics — `image-forensics-suite` 1.6.0

All metrics are computed over **content blocks only** (blocks whose local standard deviation clears
a floor), because a scanned document is mostly blank paper and including it makes every text block
look like an outlier.

| Finding | Measures | Cannot tell you | Benign causes |
|---|---|---|---|
| `IMG_ELA_LOCAL_ANOMALY` | A contiguous area whose response to controlled re-compression differs from the rest of the page, in either direction, at z ≥ 7 with effect size ≥ 0.40 | Whether the difference is an edit | A logo, a photograph, a pre-printed block, a stamp |
| `IMG_NOISE_INCONSISTENCY` | Local noise floor differing at z ≥ 9.5 | Which region is "original" | Mixed-source composites that are entirely legitimate |
| `IMG_COPY_MOVE_REGION` | ≥ 22 ORB keypoint pairs sharing one displacement, covering ≥ 0.6% of the image | Which instance is the copy | Repeated template graphics, duplicated stamps, tiled backgrounds |
| `IMG_COMPRESSION_INCONSISTENCY` | JPEG-ghost quality map: a region whose last compression quality differs from the page | Where the region came from | An embedded photograph or a low-quality logo |
| `IMG_LOW_JPEG_QUALITY` | Estimated quality below 62 | — | **Read this one carefully:** heavy compression destroys the detail the other detectors need, so an *absence* of findings on such a document is uninformative |
| `IMG_NONSTANDARD_QUANT_TABLE` | Quantisation table off the standard IJG curve | — | A specific editor or converter in the pipeline |

**Measured but not raised on text-heavy rasters:** resampling periodicity and JPEG lattice energy.
Printed text has its own regular line pitch and crisp stroke gradients, which produce exactly the
signal these metrics look for — on a document image they fire on essentially everything. Both are
computed and reported in the evidence blob with `signal_suppressed_for_text: true` and the reason.

## 4. Typography and layout — `typography-layout-forensics` 1.4.0

| Finding | Measures | Benign causes |
|---|---|---|
| `TXT_BASELINE_ANOMALY` | A word ≥ 0.34 line-heights off its line's baseline | Uneven scanning, skew, subscripts |
| `TXT_GLYPH_SIZE_ANOMALY` | Word height outside 0.66–1.42× its line's median | Deliberate emphasis; a machine-readable zone |
| `TXT_STROKE_WEIGHT_ANOMALY` | Mean stroke thickness (distance transform) deviating > 42% | Bold emphasis, ink bleed, a different pen |
| `TXT_LOW_CONFIDENCE_ISLAND` | A word recognised below 0.58 inside a line above 0.82 | A smudge, a stamp overlapping text, a fold |

## 5. Synthetic-media analysis

**The bundled provider is `demo_heuristic` (`veridoc-demo-heuristic` @ 0.4.0) — a deterministic,
explainable feature detector, not a trained classifier.** It measures eight properties with
published weights: spectral high-frequency share (0.19), noise-field uniformity (0.17), cross-channel
detail correlation (0.12), edge-gradient kurtosis (0.11), capture-provenance completeness (0.13),
text-rendering irregularity (0.12), block-variance entropy (0.09) and colour-palette density (0.07).
Scores for a lossless page render are damped by 0.82, since a vector-rendered page is not
photographic.

Output is always a **band**, never a verdict:

| Likelihood | Band | Wording shown |
|---|---|---|
| < 0.35 | `no_significant_indicators` | "No significant synthetic-media indicators detected" |
| 0.35–0.50 | `weak_indicators` | "Weak synthetic-media indicators present" |
| 0.50–0.68 | `possible_indicators` | "Potential synthetic-media indicators detected" |
| ≥ 0.68 | `notable_indicators` | "Notable synthetic-media indicators detected" |

There is no code path that can emit "definitely AI", "100% fake" or any verdict. Every result is
labelled `is_demo: true` in the API, the UI and the PDF report, and carries the provider's
disclaimer. `AIGC_SYNTHETIC_INDICATORS` therefore has a deliberately modest risk weight and the
lowest category ceiling in the engine — a heuristic indicator should not by itself move a document
into Review Recommended. A production detector behind `AIGC_PROVIDER=remote_http` warrants a higher
configured weight.

## 6. Tampering correlation — `tampering-correlation-engine` 1.5.0

Not a detector: a correlation layer over the detectors above. A signal is raised only where either a
high-reliability source fires or **two independent sources overlap on the same area**, and the
combined confidence clears 0.45.

```
combined = 1 − Π (1 − confidence_i × reliability_i)     capped at 0.93
```

Source reliabilities: exact PDF font mix 0.90, copy-move 0.85, PDF annotation 0.75, ELA 0.72, local
compression quality 0.70, stroke weight 0.66, noise 0.60, baseline 0.58, glyph size 0.54,
low-confidence island 0.48.

The region is then named by intersecting it with extracted fields, which produces the tamper type:
`edited_amount`, `modified_date`, `altered_identifier`, `replaced_name`, `copy_paste_region`,
`overlay_annotation`, `image_replacement`, `added_text`, `font_substitution`,
`signature_or_stamp`, or `region_anomaly` when it covers no extracted value.

## 7. Consistency rules — `consistency-rule-engine`, rules `2026.09.1`

Deterministic, and therefore the most trustworthy signals in the platform — subject to extraction
being correct, which is why every rule finding carries the fields it used and every extracted value
carries its own confidence and bounding box.

Arithmetic: `LINE_ITEM_SUM_MISMATCH`, `TOTAL_ARITHMETIC_MISMATCH`, `TAX_CALCULATION_MISMATCH`,
`BALANCE_MISMATCH`, `AMOUNT_PAID_EXCEEDS_TOTAL`, `NON_POSITIVE_TOTAL`, `DUPLICATE_LINE_ITEMS`.

Dates: `TREATMENT_AFTER_INVOICE`, `ADMISSION_AFTER_DISCHARGE`, `FUTURE_DATED_DOCUMENT`,
`IMPLAUSIBLE_DATE_OF_BIRTH`, `DOCUMENT_EXPIRED_AT_EVENT`, `SERVICE_OUTSIDE_POLICY_WINDOW`.

Identity and format: `MISSING_REQUIRED_FIELD`, `IDENTIFIER_FORMAT_UNEXPECTED`,
`INTERNAL_NAME_MISMATCH`, `VIN_CHECK_DIGIT_INVALID` (ISO 3779), `IBAN_CHECKSUM_INVALID` (ISO 13616
mod-97), `CURRENCY_AMBIGUOUS`, `LOW_CONFIDENCE_CRITICAL_FIELD`.

Ingest: `DOC_DUPLICATE_CONTENT_HASH` — a byte-identical file already on record. Attributed to the
*later* submission; the document filed first records the link at informational level only.

Every rule reports three outcomes, all of which the UI shows: failed, **passed**, or not applicable
with the reason. A green tick is what makes a Low Concern verdict meaningful rather than merely
empty.

## 8. Cross-document comparison — `cross-document-comparator` 1.3.0

Compares 16 fields across a claim bundle and against the claim record, type-aware: fuzzy token-set
for names, exact-after-normalisation for identifiers, day granularity for dates, tolerance for
money.

Pairing policies prevent manufactured findings:

| Policy | Fields | Rule |
|---|---|---|
| `any` | policy number, claim number, provider, incident date, registration, VIN, currency, names | Compare across every pair holding the field |
| `same_party` | date of birth, national ID, diagnosis, treatment/admission/discharge dates | Only when both documents record the value for the same individual, resolved by subject |
| `same_invoice` | total amount | Only when both cite the same invoice, or one is a settlement document for the other |

Identity subject resolution matters: a date of birth on a hospital invoice belongs to the *patient*,
not the policyholder who submitted the claim. Same-person comparison is order-sensitive
(`token_sort_ratio ≥ 0.80`) because a shared surname is not identity — "Daniel Okonkwo" against
"Amelia R. Okonkwo" scores 0.73 and is correctly treated as a different person.

## 9. Trusted-source verification

Six demo providers, one interface, one production HTTP seam.

| Provider | Checks |
|---|---|
| `demo_policy` | Policy exists · active · named party is holder or registered dependant · date of birth · service date inside cover · amount within sum insured |
| `demo_hospital` | Provider accredited · in-network · registration number · invoice reference matches the provider's issuing format |
| `demo_invoice` | Invoice found · amount matches the issuer's record · issue date · patient |
| `demo_gov_id` | Document on record · status valid · holder name · date of birth · valid at the event date |
| `demo_vehicle` | Vehicle on record · registration active · VIN matches · registered keeper · write-off marker |
| `demo_payment` | Reference found · settled · amount matches |

Outcome grading: **match** (all evaluated checks agree), **partial match** (a peripheral check
disagrees), **mismatch** (a *critical* check disagrees — the record exists and contradicts the
document), **not found**, **unavailable** (the provider could not be reached; nothing is inferred).

Every demo response carries `is_demo_data: true` and a disclaimer stating that no external system
was contacted. Demo output can never be presented as a real-world confirmation.

## 10. What the risk score is

A triage ranking that decides how much human attention a document receives.

```
contribution = weight(code) × confidence × severity_multiplier
category_score = cap × (1 − exp(−1.3 × Σ contributions / cap))
score = round(100 × Σ category_scores / 72)
```

Severity multipliers: info 0.35, low 0.60, medium 1.00, high 1.35, critical 1.60.
Category ceilings: verification 70, tampering 58, consistency 50, cross-document 50, security 40,
forensics 34, metadata 24, synthetic media 20.

Bands: Low Concern < 40, Review Recommended 40–74, High Concern ≥ 75 (all configurable).

It is **not** a probability that fraud occurred, and no combination of signals in this platform can
establish that a document is fake. Dismissed findings are excluded from the score with the exclusion
reported; confirmed findings are treated as established. Corroborating verification can apply a
small credit, capped at 6 points, and is suppressed entirely when any high or critical finding is
present.

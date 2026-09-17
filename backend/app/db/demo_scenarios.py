"""Demo claim bundles.

Ten claims, twenty-two documents, covering the six required scenarios:

  1. Clean legitimate document              CLM-2026-000101 / CLM-2026-000106
  2. Edited invoice amount                  CLM-2026-000102 (DOC 4)
  3. Metadata anomaly                       CLM-2026-000105 (DOC 12)
  4. Cross-document mismatch                CLM-2026-000102 (DOC 4 vs DOC 5)
  5. Potential synthetic image              CLM-2026-000108 (DOC 18)
  6. External verification mismatch         CLM-2026-000102, 000104, 000109

Plus: spliced photograph (000103), duplicate-content re-upload (000110),
editor metadata on a photo (000110), invalid VIN check digit (000108) and a
lapsed policy outside its cover window (000104).

The anomalies are built into the files themselves - see ``demo_documents.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.db.demo_documents import DocSpec
from app.db.enums import DocumentSource

MERIDIAN = "Meridian General Hospital"
MERIDIAN_SUB = "Ashford NHS Foundation Trust · Provider registration HRG-114-882"
COLUMBA = "St Columba Medical Centre"
NORTHGATE = "Northgate Day Surgery"
LAKESIDE = "Lakeside Wellness Clinic"
GARAGE = "Ashford Collision Centre"
INSURER = "Northbridge Mutual"

FOOTER_INVOICE = ("Payment due within 30 days. Queries to billing@meridian-general.example "
                  "quoting the invoice number. This document is issued electronically.")


def dt(y, m, d, hh=9, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


@dataclass
class DemoDocument:
    spec: DocSpec
    filename: str
    source: str = DocumentSource.PORTAL_UPLOAD
    uploaded_by: str = "claims@veridoc.example"
    uploaded_at: datetime = field(default_factory=lambda: dt(2026, 9, 1))
    scenario: str = ""
    duplicate_of: str | None = None


@dataclass
class DemoClaim:
    claim_number: str
    customer_name: str
    customer_dob: date
    policy_number: str
    claim_type: str
    claimed_amount: str
    currency: str
    incident_date: date
    summary: str
    created_by: str
    assigned_investigator: str | None
    customer_email: str
    documents: list[DemoDocument]


def _invoice_spec(**kw) -> DocSpec:
    base = dict(kind="pdf", title="Medical Invoice", organisation=MERIDIAN,
                org_subtitle=MERIDIAN_SUB, footer=FOOTER_INVOICE,
                item_header=("Description", "Qty", "Unit price", "Amount"),
                signature_line="Authorised by Finance Office, Meridian General Hospital")
    base.update(kw)
    return DocSpec(**base)


CLAIMS: list[DemoClaim] = [
    # ---------------------------------------------------------------- CLAIM 1
    DemoClaim(
        claim_number="CLM-2026-000101", customer_name="Amelia R. Okonkwo",
        customer_dob=date(1986, 4, 12), policy_number="POL-938472", claim_type="health",
        claimed_amount="4820.00", currency="USD", incident_date=date(2026, 8, 15),
        summary=("Inpatient treatment for dependant Daniel Okonkwo at Meridian General "
                 "Hospital. Invoice, prescription and policyholder identity submitted."),
        created_by="claims@veridoc.example", assigned_investigator=None,
        customer_email="a.okonkwo@example.com",
        documents=[
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="meridian-invoice-MGH-2026-004417.pdf",
                uploaded_at=dt(2026, 8, 18, 11, 12),
                spec=_invoice_spec(
                    key="d01",
                    party_fields=[
                        ("Patient name", "Daniel Okonkwo"),
                        ("Date of birth", "2014-03-09"),
                        ("Insured name", "Amelia R. Okonkwo"),
                        ("Policy number", "POL-938472"),
                    ],
                    header_fields=[
                        ("Invoice number", "MGH-2026-004417"),
                        ("Invoice date", "2026-08-18"),
                        ("Treatment date", "2026-08-15"),
                        ("Department", "Paediatric Orthopaedics"),
                        ("Physician", "Dr Helena Voss"),
                        ("Currency", "USD"),
                    ],
                    items=[
                        ("Consultation - paediatric orthopaedics", "1", "2,450.00", "2,450.00"),
                        ("Radiography - left forearm, 2 views", "2", "790.00", "1,580.00"),
                        ("Fibreglass cast application", "1", "790.00", "790.00"),
                    ],
                    totals=[("Subtotal", "$4,820.00"), ("Tax", "$0.00"),
                            ("Total amount", "$4,820.00")],
                    creator="Meridian Billing Suite 11.2",
                    producer="Meridian Billing Suite 11.2 (PDF export)",
                    created_at=dt(2026, 8, 18, 10, 41), modified_at=dt(2026, 8, 18, 10, 41),
                    seed=101,
                ),
            ),
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="meridian-prescription-RX-2026-88410.pdf",
                uploaded_at=dt(2026, 8, 18, 11, 14),
                spec=DocSpec(
                    key="d02", kind="pdf", title="Prescription", organisation=MERIDIAN,
                    org_subtitle=MERIDIAN_SUB,
                    party_fields=[("Patient name", "Daniel Okonkwo"),
                                  ("Date of birth", "2014-03-09")],
                    header_fields=[("Prescription no", "RX-2026-88410"),
                                   ("Prescription date", "2026-08-15"),
                                   ("Prescriber", "Dr Helena Voss"),
                                   ("Diagnosis", "Closed fracture, left radius")],
                    item_header=("Medication", "Dose", "Frequency", "Days"),
                    items=[("Paracetamol 250mg suspension", "5 ml", "Four times daily", "5"),
                           ("Ibuprofen 100mg suspension", "5 ml", "Three times daily", "3")],
                    body_paragraphs=[
                        "Dispense as written. Review in fracture clinic after 14 days.",
                    ],
                    signature_line="Dr Helena Voss, MBBS MRCS - registration GMC 7741203",
                    footer="Prescription valid for 6 months from the date of issue.",
                    creator="Meridian Clinical Suite 8.4",
                    producer="Meridian Clinical Suite 8.4 (PDF export)",
                    created_at=dt(2026, 8, 15, 16, 22), modified_at=dt(2026, 8, 15, 16, 22),
                    seed=102,
                ),
            ),
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="policyholder-passport-card.png",
                uploaded_at=dt(2026, 8, 18, 11, 16),
                spec=DocSpec(
                    key="d03", kind="card_png", title="Identity Card",
                    organisation="HM Passport Office",
                    org_subtitle="United Kingdom of Great Britain and Northern Ireland",
                    party_fields=[("Full name", "AMELIA R OKONKWO"),
                                  ("Date of birth", "1986-04-12")],
                    header_fields=[("Document no", "PN-4471829"), ("Nationality", "BRITISH"),
                                   ("Sex", "F"), ("Expiry date", "2031-05-19")],
                    signature_line="A. R. Okonkwo",
                    footer="P<GBROKONKWO<<AMELIA<R<<<<<<<<<<<<<<<<<<<<<",
                    seed=103,
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------- CLAIM 2
    DemoClaim(
        claim_number="CLM-2026-000102", customer_name="Amelia R. Okonkwo",
        customer_dob=date(1986, 4, 12), policy_number="POL-938472", claim_type="health",
        claimed_amount="8500.00", currency="USD", incident_date=date(2026, 8, 24),
        summary=("Day-case procedure claimed at 8,500.00. The submitted invoice total does not "
                 "reconcile with its own line items or with the claim form."),
        created_by="claims@veridoc.example",
        assigned_investigator="investigator@veridoc.example",
        customer_email="a.okonkwo@example.com",
        documents=[
            DemoDocument(
                scenario="2 - edited invoice amount / 6 - verification mismatch",
                filename="meridian-invoice-MGH-2026-004918.pdf",
                uploaded_at=dt(2026, 8, 28, 9, 5),
                spec=_invoice_spec(
                    key="d04",
                    party_fields=[
                        ("Patient name", "Amelia R. Okonkwo"),
                        ("Date of birth", "1986-04-12"),
                        ("Insured name", "Amelia R. Okonkwo"),
                        ("Policy number", "POL-938472"),
                    ],
                    header_fields=[
                        ("Invoice number", "MGH-2026-004918"),
                        ("Invoice date", "2026-08-27"),
                        ("Treatment date", "2026-08-24"),
                        ("Department", "General Surgery"),
                        ("Physician", "Mr A. Farhadi"),
                        ("Currency", "USD"),
                    ],
                    items=[
                        ("Day-case theatre time (90 min)", "1", "2,400.00", "2,400.00"),
                        ("Surgeon fee - laparoscopic procedure", "1", "1,850.00", "1,850.00"),
                        ("Anaesthetist fee", "1", "1,250.00", "1,250.00"),
                        ("Recovery ward and consumables", "1", "1,000.00", "1,000.00"),
                    ],
                    totals=[("Subtotal", "$6,500.00"), ("Tax", "$0.00"),
                            ("Total amount", "$8,500.00")],
                    font_anomaly_field="Total amount",
                    baseline_shift_field="Total amount",
                    annotation_overlay=("Total amount", "$8,500.00"),
                    creator="Meridian Billing Suite 11.2",
                    producer="Meridian Billing Suite 11.2 (PDF export)",
                    created_at=dt(2026, 8, 27, 14, 2), modified_at=dt(2026, 8, 28, 1, 47),
                    seed=104,
                ),
            ),
            DemoDocument(
                scenario="4 - cross-document mismatch",
                filename="claim-form-CLM-2026-000102.pdf",
                uploaded_at=dt(2026, 8, 28, 9, 7),
                spec=DocSpec(
                    key="d05", kind="pdf", title="Claim Form", organisation=INSURER,
                    org_subtitle="Health claims - part A: to be completed by the insured",
                    party_fields=[("Insured name", "Amelia R. Okonkwo"),
                                  ("Patient name", "Amelia R. Okonkwo"),
                                  ("Date of birth", "1986-04-12"),
                                  ("Policy number", "POL-938472")],
                    header_fields=[("Claim number", "CLM-2026-000102"),
                                   ("Hospital", MERIDIAN),
                                   ("Treatment date", "2026-08-24"),
                                   ("Diagnosis", "Symptomatic cholelithiasis"),
                                   ("Currency", "USD")],
                    totals=[("Total amount", "$6,500.00")],
                    body_paragraphs=[
                        ("Declaration by the insured: I declare that the information given in "
                         "this claim form is true and complete to the best of my knowledge, and "
                         "that the amount claimed reflects the charges actually incurred."),
                        ("Nature of claim: day-case laparoscopic procedure. Bank details for "
                         "settlement provided separately under part C."),
                    ],
                    signature_line="Signature of insured - A. R. Okonkwo, 2026-08-27",
                    footer="Northbridge Mutual - claims intake, Ashford. Form NM-HC-04 rev 2026.1",
                    creator="Northbridge Forms 4.1", producer="Northbridge Forms 4.1",
                    created_at=dt(2026, 8, 27, 18, 30), modified_at=dt(2026, 8, 27, 18, 30),
                    seed=105,
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------- CLAIM 3
    DemoClaim(
        claim_number="CLM-2026-000103", customer_name="Marcus Lindqvist",
        customer_dob=date(1979, 11, 3), policy_number="POL-551204", claim_type="motor",
        claimed_amount="3150.00", currency="USD", incident_date=date(2026, 7, 2),
        summary=("Motor collision on the Ashford ring road. Repair estimate, registration "
                 "document, police report and a photographed payment receipt submitted."),
        created_by="claims2@veridoc.example",
        assigned_investigator="investigator2@veridoc.example",
        customer_email="m.lindqvist@example.com",
        documents=[
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="collision-centre-estimate-EST-2026-3391.pdf",
                uploaded_at=dt(2026, 7, 6, 10, 2), uploaded_by="claims2@veridoc.example",
                spec=DocSpec(
                    key="d06", kind="pdf", title="Repair Estimate", organisation=GARAGE,
                    org_subtitle="Approved motor body repairer · VAT 442 118 77",
                    party_fields=[("Customer name", "Marcus Lindqvist"),
                                  ("Policy number", "POL-551204"),
                                  ("Registration number", "KPL-4472"),
                                  ("VIN", "WBA3A5C57FF123456")],
                    header_fields=[("Estimate no", "EST-2026-3391"),
                                   ("Invoice date", "2026-07-06"),
                                   ("Incident date", "2026-07-02"),
                                   ("Make", "BMW"), ("Model", "320i"),
                                   ("Odometer", "84120")],
                    item_header=("Repair operation", "Hours", "Rate", "Amount"),
                    items=[("Front bumper assembly - replace", "1", "1,150.00", "1,150.00"),
                           ("Nearside wing - repair and refinish", "6", "100.00", "600.00"),
                           ("Paint labour and materials", "8", "100.00", "800.00"),
                           ("Headlamp unit - replace", "1", "600.00", "600.00")],
                    totals=[("Parts total", "$1,750.00"), ("Labour total", "$1,400.00"),
                            ("Subtotal", "$3,150.00"), ("Tax", "$0.00"),
                            ("Total amount", "$3,150.00")],
                    signature_line="Estimator - K. Ahsan, ATA accredited",
                    footer="Estimate valid 30 days. Subject to insurer authorisation.",
                    creator="BodyShopPro 9", producer="BodyShopPro 9 PDF writer",
                    created_at=dt(2026, 7, 6, 9, 15), modified_at=dt(2026, 7, 6, 9, 15),
                    seed=106,
                ),
            ),
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="vehicle-registration-KPL-4472.pdf",
                uploaded_at=dt(2026, 7, 6, 10, 4), uploaded_by="claims2@veridoc.example",
                spec=DocSpec(
                    key="d07", kind="pdf", title="Certificate of Registration",
                    organisation="Driver & Vehicle Licensing Agency",
                    org_subtitle="Vehicle registration certificate (V5C equivalent)",
                    party_fields=[("Customer name", "Marcus Lindqvist"),
                                  ("Address", "18 Harrow Court, Ashford")],
                    header_fields=[("Registration number", "KPL-4472"),
                                   ("VIN", "WBA3A5C57FF123456"), ("Make", "BMW"),
                                   ("Model", "320i"), ("Year", "2015"),
                                   ("Issue date", "2015-04-22"),
                                   ("Issuing authority", "DVLA Swansea")],
                    body_paragraphs=[
                        ("This certificate records the registered keeper of the vehicle. It is "
                         "not proof of legal ownership."),
                    ],
                    footer="DVLA - Swansea SA99 1BA. Class of vehicle: private car.",
                    creator="DVLA Document Service", producer="DVLA Document Service",
                    created_at=dt(2015, 4, 22, 8, 0), modified_at=dt(2015, 4, 22, 8, 0),
                    seed=107,
                ),
            ),
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="police-report-FIR-2026-0771.pdf",
                uploaded_at=dt(2026, 7, 6, 10, 6), uploaded_by="claims2@veridoc.example",
                spec=DocSpec(
                    key="d08", kind="pdf", title="Police Report",
                    organisation="Ashford Constabulary",
                    org_subtitle="Road traffic collision report - general diary extract",
                    party_fields=[("Customer name", "Marcus Lindqvist"),
                                  ("Registration number", "KPL-4472")],
                    header_fields=[("Report no", "FIR-2026-0771"),
                                   ("Incident date", "2026-07-02"),
                                   ("Location", "Ashford Ring Road, junction 4"),
                                   ("Officer", "Insp. M. Halvorsen"),
                                   ("Issue date", "2026-07-03")],
                    body_paragraphs=[
                        ("At approximately 18:40 on 2 July 2026 a two-vehicle collision was "
                         "reported at junction 4 of the Ashford ring road. No injuries were "
                         "recorded. Vehicle KPL-4472 sustained damage to the front bumper, "
                         "nearside wing and offside headlamp unit."),
                        ("Statements were taken from both drivers and one independent witness. "
                         "No offences were recorded at the scene."),
                    ],
                    signature_line="Insp. M. Halvorsen, warrant 44118",
                    footer="Extract issued for insurance purposes. Ashford Constabulary.",
                    creator="Constabulary Records System", producer="Constabulary Records System",
                    created_at=dt(2026, 7, 3, 11, 30), modified_at=dt(2026, 7, 3, 11, 30),
                    seed=108,
                ),
            ),
            DemoDocument(
                scenario="tampered photograph - amounts block overwritten after capture",
                filename="collision-centre-receipt-photo.jpg",
                uploaded_at=dt(2026, 7, 7, 15, 41), uploaded_by="claims2@veridoc.example",
                spec=DocSpec(
                    key="d09", kind="photo_jpeg", title="Payment Receipt",
                    organisation=GARAGE, org_subtitle="Approved motor body repairer",
                    party_fields=[("Customer name", "Marcus Lindqvist"),
                                  ("Registration number", "KPL-4472")],
                    header_fields=[("Receipt number", "RCP-2026-8841"),
                                   ("Invoice date", "2026-07-07"),
                                   ("Payment method", "Card ending 4471")],
                    item_header=("Description", "", "", "Amount"),
                    items=[("Repair works per estimate EST-2026-3391", "", "", "3,150.00")],
                    totals=[("Subtotal", "$3,150.00"), ("Total amount", "$3,150.00"),
                            ("Amount paid", "$3,150.00")],
                    footer="Received with thanks. Ashford Collision Centre.",
                    signature_line="Received by: front desk",
                    splice_region_label="Total amount", copy_move_graphic=True,
                    camera=("Apple", "iPhone 13"),
                    exif_capture=dt(2026, 7, 7, 15, 12), exif_modified=dt(2026, 7, 7, 15, 12),
                    jpeg_quality=88, seed=109,
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------- CLAIM 4
    DemoClaim(
        claim_number="CLM-2026-000104", customer_name="Priya Raghunathan",
        customer_dob=date(1991, 7, 22), policy_number="POL-770311", claim_type="health",
        claimed_amount="1980.00", currency="USD", incident_date=date(2026, 6, 28),
        summary=("Treatment claimed at a clinic with no accreditation record, under a policy "
                 "that had lapsed before the date of service."),
        created_by="claims@veridoc.example",
        assigned_investigator="investigator@veridoc.example",
        customer_email="p.raghunathan@example.com",
        documents=[
            DemoDocument(
                scenario="6 - external verification mismatch (provider + policy)",
                filename="lakeside-hospital-bill-LWC-2026-0219.pdf",
                uploaded_at=dt(2026, 7, 1, 8, 30),
                spec=DocSpec(
                    key="d10", kind="pdf", title="Hospital Bill", organisation=LAKESIDE,
                    org_subtitle="Wellness and day-care services",
                    party_fields=[("Patient name", "Priya Raghunathan"),
                                  ("Date of birth", "1991-07-22"),
                                  ("Insured name", "Priya Raghunathan"),
                                  ("Policy number", "POL-770311")],
                    header_fields=[("Bill number", "LWC-2026-0219"),
                                   ("Invoice date", "2026-06-28"),
                                   ("Admission date", "2026-06-26"),
                                   ("Discharge date", "2026-06-28"),
                                   ("Diagnosis", "Acute gastritis"),
                                   ("Currency", "USD")],
                    item_header=("Charge line", "Qty", "Unit price", "Amount"),
                    items=[("Day-care bed charges", "3", "320.00", "960.00"),
                           ("Intravenous therapy and consumables", "1", "540.00", "540.00"),
                           ("Pathology panel", "1", "280.00", "280.00"),
                           ("Consultation - internal medicine", "2", "100.00", "200.00")],
                    totals=[("Subtotal", "$1,980.00"), ("Tax", "$0.00"),
                            ("Total amount", "$1,980.00")],
                    signature_line="Accounts - Lakeside Wellness Clinic",
                    footer="Settlement by bank transfer. Reference the bill number.",
                    creator="Word", producer="Microsoft: Print To PDF",
                    created_at=dt(2026, 6, 29, 22, 14), modified_at=dt(2026, 6, 30, 3, 8),
                    seed=110,
                ),
            ),
            DemoDocument(
                scenario="6 - external verification mismatch (payment returned)",
                filename="bank-payment-advice-TRN-20260705-118093.pdf",
                uploaded_at=dt(2026, 7, 8, 12, 15),
                spec=DocSpec(
                    key="d11", kind="pdf", title="Payment Advice",
                    organisation="Meridian Bank plc",
                    org_subtitle="Outward payment advice - business banking",
                    party_fields=[("Customer name", "Priya Raghunathan"),
                                  ("Account number", "GB29NWBK60161331926819"),
                                  ("Bank name", "Meridian Bank plc")],
                    header_fields=[("Transaction reference", "TRN-20260705-118093"),
                                   ("Invoice date", "2026-07-05"),
                                   ("Payment method", "Faster payment"),
                                   ("Currency", "USD")],
                    item_header=("Transaction", "Value date", "Type", "Amount"),
                    items=[("Payment to Lakeside Wellness Clinic", "2026-07-05", "DR",
                            "1,980.00")],
                    totals=[("Amount paid", "$1,980.00")],
                    body_paragraphs=[
                        ("This advice confirms that the instruction above was submitted for "
                         "processing. Settlement is subject to confirmation by the beneficiary "
                         "bank."),
                    ],
                    footer="Meridian Bank plc is authorised and regulated. Advice ref A-118093.",
                    creator="Meridian Bank Statements", producer="Meridian Bank Statements",
                    created_at=dt(2026, 7, 5, 18, 2), modified_at=dt(2026, 7, 5, 18, 2),
                    seed=111,
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------- CLAIM 5
    DemoClaim(
        claim_number="CLM-2026-000105", customer_name="Tobias Beaumont",
        customer_dob=date(1968, 2, 17), policy_number="POL-284915", claim_type="health",
        claimed_amount="2150.00", currency="USD", incident_date=date(2026, 6, 21),
        summary=("Day surgery invoice that reconciles against the issuer, but whose PDF "
                 "metadata and object structure show editing after production."),
        created_by="claims@veridoc.example", assigned_investigator=None,
        customer_email="t.beaumont@example.com",
        documents=[
            DemoDocument(
                scenario="3 - metadata anomaly",
                filename="northgate-invoice-NDS-2026-000742.pdf",
                uploaded_at=dt(2026, 6, 24, 9, 48),
                spec=_invoice_spec(
                    key="d12", organisation=NORTHGATE,
                    org_subtitle="Independent day-surgery unit · Provider registration HRG-501-773",
                    party_fields=[("Patient name", "Tobias Beaumont"),
                                  ("Date of birth", "1968-02-17"),
                                  ("Insured name", "Tobias Beaumont"),
                                  ("Policy number", "POL-284915")],
                    header_fields=[("Invoice number", "NDS-2026-000742"),
                                   ("Invoice date", "2026-06-21"),
                                   ("Treatment date", "2026-06-21"),
                                   ("Department", "Ophthalmology"),
                                   ("Physician", "Ms R. Adeyemi"),
                                   ("Currency", "USD")],
                    items=[("Cataract assessment and imaging", "1", "650.00", "650.00"),
                           ("Day-case theatre time (45 min)", "1", "900.00", "900.00"),
                           ("Intraocular lens - monofocal", "1", "600.00", "600.00")],
                    totals=[("Subtotal", "$2,150.00"), ("Tax", "$0.00"),
                            ("Total amount", "$2,150.00")],
                    creator="Microsoft Word",
                    producer="Adobe Photoshop 25.3 (Windows)",
                    created_at=dt(2026, 6, 21, 10, 14),
                    modified_at=dt(2026, 6, 19, 8, 2),          # earlier than creation
                    incremental_update=True, trailing_bytes=2600,
                    footer=("Northgate Day Surgery, 4 Northgate Mews. Payment within 30 days."),
                    signature_line="Authorised by Northgate Day Surgery accounts",
                    seed=112,
                ),
            ),
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="insurance-certificate-POL-284915.pdf",
                uploaded_at=dt(2026, 6, 24, 9, 50),
                spec=DocSpec(
                    key="d13", kind="pdf", title="Certificate of Insurance",
                    organisation=INSURER, org_subtitle="Health Secure - individual cover",
                    party_fields=[("Insured name", "Tobias Beaumont"),
                                  ("Date of birth", "1968-02-17"),
                                  ("Address", "77 Bellhouse Row, Ashford")],
                    header_fields=[("Policy number", "POL-284915"),
                                   ("Certificate number", "CRT-284915-01"),
                                   ("Insurer", INSURER), ("Valid from", "2026-03-01"),
                                   ("Valid to", "2027-02-28"),
                                   ("Coverage amount", "$80,000.00"),
                                   ("Issue date", "2026-02-24")],
                    body_paragraphs=[
                        ("This certificate evidences that the policy named above is in force for "
                         "the period of insurance shown, subject to the policy terms, exclusions "
                         "and any endorsements issued."),
                    ],
                    signature_line="For and on behalf of Northbridge Mutual",
                    footer="Certificate issued electronically. Verify at northbridge.example.",
                    creator="Northbridge Policy Admin", producer="Northbridge Policy Admin",
                    created_at=dt(2026, 2, 24, 7, 45), modified_at=dt(2026, 2, 24, 7, 45),
                    seed=113,
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------- CLAIM 6
    DemoClaim(
        claim_number="CLM-2026-000106", customer_name="Sofia Almeida",
        customer_dob=date(1994, 9, 30), policy_number="POL-613027", claim_type="travel",
        claimed_amount="340.00", currency="USD", incident_date=date(2026, 7, 9),
        summary="Out-patient consultation abroad. Receipt and prescription reconcile cleanly.",
        created_by="claims@veridoc.example", assigned_investigator=None,
        customer_email="s.almeida@example.com",
        documents=[
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="columba-receipt-SCM-2026-001188.pdf",
                uploaded_at=dt(2026, 7, 11, 13, 20),
                spec=DocSpec(
                    key="d14", kind="pdf", title="Payment Receipt", organisation=COLUMBA,
                    org_subtitle="Provider registration HRG-229-104 · Ashford",
                    party_fields=[("Patient name", "Sofia Almeida"),
                                  ("Date of birth", "1994-09-30")],
                    header_fields=[("Receipt number", "SCM-2026-001188"),
                                   ("Invoice number", "SCM-2026-001188"),
                                   ("Invoice date", "2026-07-09"),
                                   ("Payment method", "Cash"), ("Currency", "USD")],
                    items=[("Out-patient consultation - general practice", "1", "240.00",
                            "240.00"),
                           ("Rapid diagnostic test", "1", "80.00", "80.00")],
                    totals=[("Subtotal", "$320.00"), ("Tax", "$20.00"),
                            ("Total amount", "$340.00"), ("Amount paid", "$340.00")],
                    footer="Received with thanks. St Columba Medical Centre.",
                    signature_line="Received by: reception desk",
                    creator="Columba Practice Manager", producer="Columba Practice Manager",
                    created_at=dt(2026, 7, 9, 12, 5), modified_at=dt(2026, 7, 9, 12, 5),
                    seed=114,
                ),
            ),
            DemoDocument(
                scenario="1 - clean legitimate document",
                filename="columba-prescription-RX-2026-51120.pdf",
                uploaded_at=dt(2026, 7, 11, 13, 22),
                spec=DocSpec(
                    key="d15", kind="pdf", title="Prescription", organisation=COLUMBA,
                    org_subtitle="Provider registration HRG-229-104 · Ashford",
                    party_fields=[("Patient name", "Sofia Almeida"),
                                  ("Date of birth", "1994-09-30")],
                    header_fields=[("Prescription no", "RX-2026-51120"),
                                   ("Prescription date", "2026-07-09"),
                                   ("Prescriber", "Dr J. Nkemelu"),
                                   ("Diagnosis", "Acute bacterial pharyngitis")],
                    item_header=("Medication", "Dose", "Frequency", "Days"),
                    items=[("Amoxicillin 500mg capsules", "1 cap", "Three times daily", "7"),
                           ("Paracetamol 500mg tablets", "2 tabs", "Four times daily", "5")],
                    body_paragraphs=["Complete the full course. Return if symptoms persist."],
                    signature_line="Dr J. Nkemelu - registration GMC 6612884",
                    footer="Prescription valid for 6 months from the date of issue.",
                    creator="Columba Clinical Suite", producer="Columba Clinical Suite",
                    created_at=dt(2026, 7, 9, 12, 2), modified_at=dt(2026, 7, 9, 12, 2),
                    seed=115,
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------- CLAIM 7
    DemoClaim(
        claim_number="CLM-2026-000107", customer_name="Daniel Okonkwo",
        customer_dob=date(2014, 3, 9), policy_number="POL-938472", claim_type="health",
        claimed_amount="690.00", currency="USD", incident_date=date(2026, 9, 2),
        summary=("Follow-up consultation. The invoice bills a service dated after the invoice "
                 "itself and its tax line does not follow the stated rate."),
        created_by="claims@veridoc.example", assigned_investigator=None,
        customer_email="a.okonkwo@example.com",
        documents=[
            DemoDocument(
                scenario="internal consistency failures (dates + tax)",
                filename="meridian-invoice-MGH-2026-005130.pdf",
                uploaded_at=dt(2026, 9, 6, 10, 11),
                spec=_invoice_spec(
                    key="d16",
                    party_fields=[("Patient name", "Daniel Okonkwo"),
                                  ("Date of birth", "2014-03-09"),
                                  ("Insured name", "Amelia R. Okonkwo"),
                                  ("Policy number", "POL-938472")],
                    header_fields=[("Invoice number", "MGH-2026-005130"),
                                   ("Invoice date", "2026-09-01"),
                                   ("Treatment date", "2026-09-05"),
                                   ("Department", "Fracture Clinic"),
                                   ("Tax rate", "8%"), ("Currency", "USD")],
                    items=[("Fracture clinic review", "1", "350.00", "350.00"),
                           ("Radiography - left forearm, single view", "1", "250.00", "250.00")],
                    totals=[("Subtotal", "$600.00"), ("Tax", "$96.00"),
                            ("Total amount", "$696.00")],
                    creator="Meridian Billing Suite 11.2",
                    producer="Meridian Billing Suite 11.2 (PDF export)",
                    created_at=dt(2026, 9, 1, 16, 40), modified_at=dt(2026, 9, 1, 16, 40),
                    seed=116,
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------- CLAIM 8
    DemoClaim(
        claim_number="CLM-2026-000108", customer_name="Marcus Lindqvist",
        customer_dob=date(1979, 11, 3), policy_number="POL-551204", claim_type="motor",
        claimed_amount="5400.00", currency="USD", incident_date=date(2026, 8, 30),
        summary=("Second motor claim. The estimate repeats a line item, does not add up, and "
                 "quotes a VIN whose check digit fails. The deposit receipt is an image with "
                 "synthetic-media indicators."),
        created_by="claims2@veridoc.example",
        assigned_investigator="investigator2@veridoc.example",
        customer_email="m.lindqvist@example.com",
        documents=[
            DemoDocument(
                scenario="internal consistency failures (VIN + duplicate lines + sum)",
                filename="collision-centre-estimate-EST-2026-4417.pdf",
                uploaded_at=dt(2026, 9, 3, 8, 55), uploaded_by="claims2@veridoc.example",
                spec=DocSpec(
                    key="d17", kind="pdf", title="Repair Estimate", organisation=GARAGE,
                    org_subtitle="Approved motor body repairer · VAT 442 118 77",
                    party_fields=[("Customer name", "Marcus Lindqvist"),
                                  ("Policy number", "POL-551204"),
                                  ("Registration number", "KPL-4472"),
                                  ("VIN", "WBA3A5C51FF123456")],
                    header_fields=[("Estimate no", "EST-2026-4417"),
                                   ("Invoice date", "2026-09-02"),
                                   ("Incident date", "2026-08-30"),
                                   ("Make", "BMW"), ("Model", "320i"),
                                   ("Odometer", "86740")],
                    item_header=("Repair operation", "Hours", "Rate", "Amount"),
                    items=[("Front bumper assembly - replace", "1", "1,800.00", "1,800.00"),
                           ("Front bumper assembly - replace", "1", "1,800.00", "1,800.00"),
                           ("Paint labour and materials", "9", "100.00", "900.00"),
                           ("Panel alignment and refit", "6", "100.00", "600.00")],
                    totals=[("Parts total", "$3,600.00"), ("Labour total", "$1,800.00"),
                            ("Subtotal", "$5,400.00"), ("Tax", "$0.00"),
                            ("Total amount", "$5,400.00")],
                    signature_line="Estimator - K. Ahsan, ATA accredited",
                    footer="Estimate valid 30 days. Subject to insurer authorisation.",
                    creator="BodyShopPro 9", producer="BodyShopPro 9 PDF writer",
                    created_at=dt(2026, 9, 2, 17, 20), modified_at=dt(2026, 9, 2, 17, 20),
                    seed=117,
                ),
            ),
            DemoDocument(
                scenario="5 - potential synthetic image",
                filename="collision-centre-deposit-receipt.png",
                uploaded_at=dt(2026, 9, 3, 8, 58), uploaded_by="claims2@veridoc.example",
                spec=DocSpec(
                    key="d18", kind="synthetic_png", title="Payment Receipt",
                    organisation=GARAGE, org_subtitle="Approved motor body repairer",
                    party_fields=[("Customer name", "Marcus Lindqvist"),
                                  ("Registration number", "KPL-4472")],
                    header_fields=[("Receipt number", "RCP-2026-9902"),
                                   ("Invoice date", "2026-09-02"),
                                   ("Payment method", "Bank transfer")],
                    item_header=("Description", "", "", "Amount"),
                    items=[("Deposit against estimate EST-2026-4417", "", "", "5,400.00")],
                    totals=[("Subtotal", "$5,400.00"), ("Total amount", "$5,400.00"),
                            ("Amount paid", "$5,400.00")],
                    footer="Received with thanks. Ashford Collision Centre.",
                    smooth_synthetic=True, seed=118,
                ),
            ),
        ],
    ),

    # ---------------------------------------------------------------- CLAIM 9
    DemoClaim(
        claim_number="CLM-2026-000109", customer_name="Priya Raghunathan",
        customer_dob=date(1991, 7, 22), policy_number="POL-770311", claim_type="motor",
        claimed_amount="2400.00", currency="USD", incident_date=date(2026, 5, 14),
        summary=("Motor claim on a vehicle carrying a structural write-off marker, supported by "
                 "an identity document reported lost."),
        created_by="claims2@veridoc.example",
        assigned_investigator="investigator@veridoc.example",
        customer_email="p.raghunathan@example.com",
        documents=[
            DemoDocument(
                scenario="6 - external verification mismatch (write-off marker)",
                filename="vehicle-registration-RTX-9081.pdf",
                uploaded_at=dt(2026, 5, 20, 11, 5), uploaded_by="claims2@veridoc.example",
                spec=DocSpec(
                    key="d19", kind="pdf", title="Certificate of Registration",
                    organisation="Driver & Vehicle Licensing Agency",
                    org_subtitle="Vehicle registration certificate (V5C equivalent)",
                    party_fields=[("Customer name", "Priya Raghunathan"),
                                  ("Address", "5 Weaver Lane, Northgate")],
                    header_fields=[("Registration number", "RTX-9081"),
                                   ("VIN", "JTDKN3DU3A5019283"), ("Make", "Toyota"),
                                   ("Model", "Prius"), ("Year", "2011"),
                                   ("Issue date", "2019-11-08"),
                                   ("Issuing authority", "DVLA Swansea")],
                    body_paragraphs=[
                        ("This certificate records the registered keeper of the vehicle. It is "
                         "not proof of legal ownership."),
                    ],
                    footer="DVLA - Swansea SA99 1BA. Class of vehicle: private car.",
                    creator="DVLA Document Service", producer="DVLA Document Service",
                    created_at=dt(2019, 11, 8, 8, 0), modified_at=dt(2019, 11, 8, 8, 0),
                    seed=119,
                ),
            ),
            DemoDocument(
                scenario="6 - external verification mismatch (document reported lost)",
                filename="claimant-passport-card.png",
                uploaded_at=dt(2026, 5, 20, 11, 7), uploaded_by="claims2@veridoc.example",
                spec=DocSpec(
                    key="d20", kind="card_png", title="Identity Card",
                    organisation="HM Passport Office",
                    org_subtitle="United Kingdom of Great Britain and Northern Ireland",
                    party_fields=[("Full name", "PRIYA RAGHUNATHAN"),
                                  ("Date of birth", "1991-07-22")],
                    header_fields=[("Document no", "PN-9930012"), ("Nationality", "BRITISH"),
                                   ("Sex", "F"), ("Expiry date", "2028-03-14")],
                    signature_line="P. Raghunathan",
                    footer="P<GBRRAGHUNATHAN<<PRIYA<<<<<<<<<<<<<<<<<<<",
                    seed=120,
                ),
            ),
        ],
    ),

    # --------------------------------------------------------------- CLAIM 10
    DemoClaim(
        claim_number="CLM-2026-000110", customer_name="Amelia R. Okonkwo",
        customer_dob=date(1986, 4, 12), policy_number="POL-938472", claim_type="health",
        claimed_amount="1200.00", currency="USD", incident_date=date(2026, 9, 5),
        summary=("Photographed invoice whose EXIF names a raster editor, submitted together "
                 "with a byte-identical copy of an invoice already claimed under another case."),
        created_by="claims@veridoc.example",
        assigned_investigator="investigator2@veridoc.example",
        customer_email="a.okonkwo@example.com",
        documents=[
            DemoDocument(
                scenario="editor metadata on a photographed document",
                filename="meridian-invoice-photo-MGH-2026-005477.jpg",
                uploaded_at=dt(2026, 9, 12, 19, 33),
                spec=DocSpec(
                    key="d21", kind="photo_jpeg", title="Medical Invoice",
                    organisation=MERIDIAN, org_subtitle=MERIDIAN_SUB,
                    party_fields=[("Patient name", "Amelia R. Okonkwo"),
                                  ("Policy number", "POL-938472")],
                    header_fields=[("Invoice number", "MGH-2026-005477"),
                                   ("Invoice date", "2026-09-05"),
                                   ("Treatment date", "2026-09-05"),
                                   ("Currency", "USD")],
                    item_header=("Description", "", "", "Amount"),
                    items=[("Out-patient consultation - dermatology", "", "", "760.00"),
                           ("Dermatoscopy and biopsy", "", "", "440.00")],
                    totals=[("Subtotal", "$1,200.00"), ("Total amount", "$1,200.00")],
                    footer="Payment due within 30 days. Meridian General Hospital.",
                    signature_line="Authorised by Finance Office",
                    camera=("Apple", "iPhone 14"),
                    exif_software="Adobe Photoshop 25.3 (Windows)",
                    exif_capture=dt(2026, 9, 5, 9, 12),
                    exif_modified=dt(2026, 9, 11, 22, 41),
                    jpeg_quality=86, seed=121,
                ),
            ),
            DemoDocument(
                scenario="duplicate content across claims",
                filename="meridian-invoice-MGH-2026-004417-copy.pdf",
                uploaded_at=dt(2026, 9, 12, 19, 36),
                duplicate_of="d01",
                spec=_invoice_spec(key="d22"),   # bytes copied from d01
            ),
        ],
    ),
]


REVIEW_SCRIPT = [
    # (claim_number, actor_email, action, target, reason)
    ("CLM-2026-000101", "claims@veridoc.example", "mark_document_verified", "first_document",
     "Invoice, prescription and identity all reconcile and the issuer confirmed the reference. "
     "Verified for settlement."),
    ("CLM-2026-000101", "claims@veridoc.example", "claim_decision", "approve",
     "All three documents verified against the policy and the issuing provider. No outstanding "
     "findings. Approved for payment at the invoiced amount of 4,820.00 USD."),
    ("CLM-2026-000106", "claims@veridoc.example", "mark_document_verified", "first_document",
     "Receipt reconciles with the issuer record and the prescription is consistent. Verified."),
    ("CLM-2026-000106", "claims@veridoc.example", "claim_decision", "approve",
     "Travel out-patient claim fully corroborated by the provider record. Approved at 340.00 USD."),
    ("CLM-2026-000102", "investigator@veridoc.example", "confirm_top_finding", None,
     "Confirmed: the invoice total is set in a different typeface from its own line, sits off the "
     "baseline, and the issuer records 6,500.00 for this reference. The claim form also states "
     "6,500.00. Treated as an established discrepancy pending the provider's written copy."),
    ("CLM-2026-000102", "investigator@veridoc.example", "note",
     "Requested a signed copy of invoice MGH-2026-004918 directly from Meridian General Hospital "
     "finance office. Awaiting reply; claimant informed that settlement is on hold.", None),
    ("CLM-2026-000104", "investigator@veridoc.example", "note",
     "Lakeside Wellness Clinic has no accreditation record and the policy had lapsed on "
     "2026-01-31, before the 2026-06-28 date of service. Two independent grounds to decline. "
     "Referred to the provider-network team for a wider look at Lakeside referrals.", None),
    ("CLM-2026-000109", "investigator2@veridoc.example", "note",
     "Vehicle RTX-9081 carries a category S structural write-off marker from 2024 and the "
     "supporting passport was reported lost. Requested the engineer's report and an alternative "
     "identity document before the claim proceeds.", None),
    ("CLM-2026-000103", "investigator2@veridoc.example", "dismiss_weakest_finding", None,
     "The duplicated graphic is the garage's pre-printed SETTLED stamp, which appears twice on "
     "their stationery. Verified against two other receipts from the same repairer. Not evidence "
     "of manipulation; the spliced amount region remains open."),
]

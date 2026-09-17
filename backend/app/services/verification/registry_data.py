"""Bundled sample registry backing the demo verification providers.

This is fixture data, deliberately obvious as such: fictional insurer, hospitals
and authorities. It is the *only* source the demo providers read from, so demo
answers are deterministic and reviewable.

Kept in sync with ``app/db/seed_data.py`` so the seeded demo claims resolve to
meaningful verification outcomes - including deliberate mismatches, because a
verification layer that always says YES demonstrates nothing.
"""
from __future__ import annotations

POLICIES: dict[str, dict] = {
    "POL-938472": {
        "policy_number": "POL-938472", "status": "active",
        "holder_name": "Amelia R. Okonkwo", "holder_dob": "1986-04-12",
        "product": "Northbridge Health Secure - Family",
        "sum_insured": "60000.00", "currency": "USD",
        "valid_from": "2026-01-01", "valid_to": "2026-12-31",
        "dependants": ["Daniel Okonkwo", "Grace Okonkwo"],
        "insurer": "Northbridge Mutual",
    },
    "POL-551204": {
        "policy_number": "POL-551204", "status": "active",
        "holder_name": "Marcus Lindqvist", "holder_dob": "1979-11-03",
        "product": "Northbridge Motor Comprehensive",
        "sum_insured": "42000.00", "currency": "USD",
        "valid_from": "2025-09-15", "valid_to": "2026-09-14",
        "vehicles": ["KPL-4472"], "insurer": "Northbridge Mutual",
    },
    "POL-770311": {
        "policy_number": "POL-770311", "status": "lapsed",
        "holder_name": "Priya Raghunathan", "holder_dob": "1991-07-22",
        "product": "Northbridge Health Essential",
        "sum_insured": "25000.00", "currency": "USD",
        "valid_from": "2025-02-01", "valid_to": "2026-01-31",
        "lapse_reason": "premium_unpaid", "insurer": "Northbridge Mutual",
    },
    "POL-284915": {
        "policy_number": "POL-284915", "status": "active",
        "holder_name": "Tobias Beaumont", "holder_dob": "1968-02-17",
        "product": "Northbridge Health Secure - Individual",
        "sum_insured": "80000.00", "currency": "USD",
        "valid_from": "2026-03-01", "valid_to": "2027-02-28",
        "insurer": "Northbridge Mutual",
    },
    "POL-613027": {
        "policy_number": "POL-613027", "status": "active",
        "holder_name": "Sofia Almeida", "holder_dob": "1994-09-30",
        "product": "Northbridge Travel Plus",
        "sum_insured": "15000.00", "currency": "USD",
        "valid_from": "2026-05-01", "valid_to": "2026-10-31",
        "insurer": "Northbridge Mutual",
    },
}

HOSPITALS: dict[str, dict] = {
    "MERIDIANGENERALHOSPITAL": {
        "name": "Meridian General Hospital", "registration": "HRG-114-882",
        "status": "accredited", "city": "Ashford", "country": "GB",
        "network_member": True, "specialities": ["cardiology", "orthopaedics", "emergency"],
        "invoice_prefixes": ["MGH-", "INV-MGH"],
    },
    "STCOLUMBAMEDICALCENTRE": {
        "name": "St Columba Medical Centre", "registration": "HRG-229-104",
        "status": "accredited", "city": "Ashford", "country": "GB",
        "network_member": True, "specialities": ["general practice", "diagnostics"],
        "invoice_prefixes": ["SCM-"],
    },
    "NORTHGATEDAYSURGERY": {
        "name": "Northgate Day Surgery", "registration": "HRG-501-773",
        "status": "accredited", "city": "Northgate", "country": "GB",
        "network_member": False, "specialities": ["day surgery"],
        "invoice_prefixes": ["NDS-"],
    },
    "LAKESIDEWELLNESSCLINIC": {
        "name": "Lakeside Wellness Clinic", "registration": None,
        "status": "not_registered", "city": "unknown", "country": "unknown",
        "network_member": False, "specialities": [],
        "note": "No accreditation record held in the sample registry.",
    },
}

INVOICES: dict[str, dict] = {
    "MGH2026004417": {
        "invoice_number": "MGH-2026-004417", "provider": "Meridian General Hospital",
        "issued_on": "2026-08-18", "total": "4820.00", "currency": "USD",
        "patient_name": "Daniel Okonkwo", "status": "issued",
    },
    "MGH2026004918": {
        "invoice_number": "MGH-2026-004918", "provider": "Meridian General Hospital",
        "issued_on": "2026-08-27", "total": "6500.00", "currency": "USD",
        "patient_name": "Amelia R. Okonkwo", "status": "issued",
        "note": "Provider records a total of 6500.00 for this reference.",
    },
    "SCM2026001188": {
        "invoice_number": "SCM-2026-001188", "provider": "St Columba Medical Centre",
        "issued_on": "2026-07-09", "total": "340.00", "currency": "USD",
        "patient_name": "Sofia Almeida", "status": "issued",
    },
    "NDS2026000742": {
        "invoice_number": "NDS-2026-000742", "provider": "Northgate Day Surgery",
        "issued_on": "2026-06-21", "total": "2150.00", "currency": "USD",
        "patient_name": "Tobias Beaumont", "status": "issued",
    },
}

GOV_IDS: dict[str, dict] = {
    "PN4471829": {
        "document_number": "PN-4471829", "type": "passport", "status": "valid",
        "full_name": "Amelia R. Okonkwo", "date_of_birth": "1986-04-12",
        "issuing_authority": "HM Passport Office", "expiry_date": "2031-05-19",
    },
    "DL88213470": {
        "document_number": "DL-88213470", "type": "driving_licence", "status": "valid",
        "full_name": "Marcus Lindqvist", "date_of_birth": "1979-11-03",
        "issuing_authority": "Driver & Vehicle Licensing Agency", "expiry_date": "2029-11-02",
    },
    "PN9930012": {
        "document_number": "PN-9930012", "type": "passport", "status": "reported_lost",
        "full_name": "Priya Raghunathan", "date_of_birth": "1991-07-22",
        "issuing_authority": "HM Passport Office", "expiry_date": "2028-03-14",
        "note": "Reported lost by the holder in the sample registry.",
    },
}

VEHICLES: dict[str, dict] = {
    "KPL4472": {
        "registration": "KPL-4472", "vin": "WBA3A5C57FF123456", "make": "BMW",
        "model": "320i", "year": 2015, "colour": "Alpine White",
        "registered_keeper": "Marcus Lindqvist", "status": "registered",
        "insurance_on_record": "POL-551204", "write_off_marker": None,
    },
    "RTX9081": {
        "registration": "RTX-9081", "vin": "JTDKN3DU3A5019283", "make": "Toyota",
        "model": "Prius", "year": 2011, "colour": "Silver",
        "registered_keeper": "Priya Raghunathan", "status": "registered",
        "write_off_marker": "category_s_2024",
        "note": "Recorded as a category S structural write-off in 2024.",
    },
}

PAYMENTS: dict[str, dict] = {
    "TRN20260819774120": {
        "reference": "TRN-20260819-774120", "status": "settled",
        "amount": "4820.00", "currency": "USD", "value_date": "2026-08-19",
        "beneficiary": "Meridian General Hospital",
    },
    "TRN20260705118093": {
        "reference": "TRN-20260705-118093", "status": "returned",
        "amount": "1980.00", "currency": "USD", "value_date": "2026-07-05",
        "beneficiary": "Lakeside Wellness Clinic",
        "note": "Payment returned by the beneficiary bank: account not found.",
    },
}


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isalnum())

"""Demo verification providers.

Each provider mirrors the shape of a real integration - a lookup key, a set of
named checks, an outcome - but answers from ``registry_data.py``. Every response
is stamped ``is_demo_data=True`` with the standard disclaimer.
"""
from __future__ import annotations

import time
from datetime import date

from app.db.enums import VerificationOutcome
from app.services.extract.normalize import (
    is_same_person,
    normalize_name,
    parse_date,
    parse_money,
)
from app.services.verification.base import (
    DEMO_DISCLAIMER,
    VerificationCheck,
    VerificationProvider,
    VerificationQuery,
    VerificationResponse,
    outcome_from_checks,
)
from app.services.verification.registry_data import (
    GOV_IDS,
    HOSPITALS,
    INVOICES,
    PAYMENTS,
    POLICIES,
    VEHICLES,
    normalize_key,
)


def _name_match(a: str | None, b: str | None, threshold: float = 0.72) -> tuple[bool | None, float | None]:
    if not a or not b:
        return None, None
    from rapidfuzz import fuzz

    score = fuzz.token_set_ratio(normalize_name(a), normalize_name(b)) / 100.0
    return score >= threshold, score


def _money_match(a, b) -> tuple[bool | None, str]:
    ma, _ = parse_money(str(a)) if a is not None else (None, None)
    mb, _ = parse_money(str(b)) if b is not None else (None, None)
    if ma is None or mb is None:
        return None, "one side missing"
    if abs(ma - mb) <= max(ma, mb) * 0 + 1:  # 1 unit tolerance
        return True, "amounts agree"
    return False, f"differ by {abs(ma - mb)}"


class _DemoBase(VerificationProvider):
    mode = "demo"

    def _respond(self, started: float, **kw) -> VerificationResponse:
        return VerificationResponse(
            latency_ms=int((time.perf_counter() - started) * 1000),
            is_demo_data=True, disclaimer=DEMO_DISCLAIMER, **kw,
        )

    def _not_found(self, started: float, what: str, key: str) -> VerificationResponse:
        return self._respond(
            started, outcome=VerificationOutcome.NOT_FOUND,
            summary=(f"No {what} matching '{key}' exists in the demo registry. In production "
                     "this would mean the reference is unknown to the source system."),
            checks=[VerificationCheck("record_exists", f"{what.title()} exists", key, None, False,
                                      "No record returned by the demo registry.")],
            raw={"query_key": key, "found": False},
        )


class DemoPolicyProvider(_DemoBase):
    key = "demo_policy"
    label = "Demo Verification Provider - Insurance Policy Registry"
    request_types = ("policy_lookup",)
    description = ("Confirms that a policy exists, is in force at the service date and that the "
                   "named party is the holder or a registered dependant.")

    def verify(self, query: VerificationQuery) -> VerificationResponse:
        started = time.perf_counter()
        policy_number = query.payload.get("policy_number")
        record = POLICIES.get(str(policy_number or "").strip().upper())
        if not record:
            normalized = {normalize_key(k): v for k, v in POLICIES.items()}
            record = normalized.get(normalize_key(policy_number))
        if not record:
            return self._not_found(started, "policy", str(policy_number))

        checks: list[VerificationCheck] = [
            VerificationCheck("policy_exists", "Policy exists", str(policy_number),
                              record["policy_number"], True, "Record located."),
            VerificationCheck(
                "policy_active", "Policy active", "active", record["status"],
                record["status"] == "active",
                "" if record["status"] == "active"
                else f"Registry status is '{record['status']}'.",
            ),
        ]

        # The date of birth on a claim document belongs to the *patient*, while
        # the register holds the policyholder's. Establish whose it is before
        # comparing, otherwise every dependant's claim reads as a mismatch.
        patient = query.payload.get("patient_name")
        holder_claimed = query.payload.get("insured_name") or query.payload.get("customer_name")
        claimant = holder_claimed or patient
        dob_subject = patient or holder_claimed
        matched_dependant = None
        if claimant:
            ok, score = _name_match(claimant, record.get("holder_name"))
            if ok is False:
                for dep in record.get("dependants") or []:
                    dep_ok, dep_score = _name_match(claimant, dep)
                    if dep_ok:
                        ok, score, matched_dependant = True, dep_score, dep
                        break
            checks.append(VerificationCheck(
                "customer_match", "Named party matches holder or dependant",
                record.get("holder_name"), claimant, ok,
                (f"Matched registered dependant '{matched_dependant}' "
                 f"(similarity {score:.2f})." if matched_dependant
                 else (f"Name similarity {score:.2f}." if score is not None
                       else "Not comparable.")),
            ))

        dob = query.payload.get("date_of_birth")
        if dob and record.get("holder_dob"):
            parsed = parse_date(str(dob))
            subject_is_holder = is_same_person(dob_subject, record.get("holder_name"))
            if matched_dependant or not subject_is_holder:
                # The policy register holds the holder's date of birth; a
                # dependant's own date of birth is not a mismatch.
                checks.append(VerificationCheck(
                    "dob_match", "Date of birth matches", record["holder_dob"],
                    parsed.isoformat() if parsed else str(dob), None,
                    (f"Not evaluated: the date of birth on this document belongs to "
                     f"{dob_subject or 'a dependant'}, not to the policyholder "
                     f"{record.get('holder_name')}."
                     + (f" '{matched_dependant}' is a registered dependant on this policy."
                        if matched_dependant else "")),
                ))
            else:
                checks.append(VerificationCheck(
                    "dob_match", "Date of birth matches", record["holder_dob"],
                    parsed.isoformat() if parsed else str(dob),
                    bool(parsed and parsed.isoformat() == record["holder_dob"]),
                ))

        service_date = parse_date(str(query.payload.get("service_date") or ""))
        if service_date:
            valid_from = date.fromisoformat(record["valid_from"])
            valid_to = date.fromisoformat(record["valid_to"])
            in_window = valid_from <= service_date <= valid_to
            checks.append(VerificationCheck(
                "date_in_cover", "Service date inside cover period",
                f"{record['valid_from']} .. {record['valid_to']}", service_date.isoformat(),
                in_window,
                "" if in_window else "Service date falls outside the policy period on record.",
            ))

        amount = query.payload.get("claimed_amount")
        if amount is not None:
            claimed, _ = parse_money(str(amount))
            limit, _ = parse_money(record["sum_insured"])
            if claimed is not None and limit is not None:
                checks.append(VerificationCheck(
                    "within_sum_insured", "Amount within sum insured",
                    f"<= {record['sum_insured']} {record['currency']}", str(claimed),
                    claimed <= limit,
                ))

        outcome = outcome_from_checks(checks, found=True)
        return self._respond(
            started, outcome=outcome,
            summary=self._summary(outcome, "policy", record["policy_number"], checks),
            checks=checks, reference_id=record["policy_number"],
            raw={"record": record, "found": True},
        )

    @staticmethod
    def _summary(outcome: str, kind: str, ref: str, checks: list[VerificationCheck]) -> str:
        failed = [c.label for c in checks if c.passed is False]
        if outcome == VerificationOutcome.MATCH:
            return (f"Demo registry confirms {kind} {ref} and all {len(checks)} checks agree with "
                    "the submitted document.")
        return (f"Demo registry located {kind} {ref} but {len(failed)} check(s) disagree: "
                f"{', '.join(failed)}.")


class DemoHospitalProvider(_DemoBase):
    key = "demo_hospital"
    label = "Demo Verification Provider - Provider Accreditation Registry"
    request_types = ("provider_lookup",)
    description = ("Confirms a hospital or clinic is accredited, in-network, and that the invoice "
                   "reference matches the provider's issuing format.")

    def verify(self, query: VerificationQuery) -> VerificationResponse:
        started = time.perf_counter()
        name = query.payload.get("hospital_name") or query.payload.get("provider_name")
        record = HOSPITALS.get(normalize_key(name))
        if not record:
            best = None
            for value in HOSPITALS.values():
                ok, score = _name_match(name, value["name"], threshold=0.8)
                if ok and (best is None or (score or 0) > best[1]):
                    best = (value, score or 0)
            record = best[0] if best else None
        if not record:
            return self._not_found(started, "provider", str(name))

        checks = [
            VerificationCheck("provider_exists", "Provider exists in registry", str(name),
                              record["name"], True),
            VerificationCheck(
                "provider_accredited", "Provider accredited", "accredited", record["status"],
                record["status"] == "accredited",
                record.get("note", "") or
                ("" if record["status"] == "accredited" else "Accreditation not on record."),
            ),
            VerificationCheck("network_member", "In-network provider", "true",
                              str(record.get("network_member")).lower(),
                              bool(record.get("network_member")),
                              "" if record.get("network_member")
                              else "Out-of-network providers may attract different cover terms."),
        ]
        registration = query.payload.get("provider_registration")
        if registration and record.get("registration"):
            checks.append(VerificationCheck(
                "registration_match", "Registration number matches", record["registration"],
                str(registration), normalize_key(registration) == normalize_key(record["registration"]),
            ))
        invoice_number = query.payload.get("invoice_number")
        prefixes = record.get("invoice_prefixes") or []
        if invoice_number and prefixes:
            ok = any(normalize_key(invoice_number).startswith(normalize_key(p)) for p in prefixes)
            checks.append(VerificationCheck(
                "invoice_prefix", "Invoice reference uses the provider's format",
                " | ".join(prefixes), str(invoice_number), ok,
                "" if ok else "Reference does not use a format this provider issues.",
            ))
        outcome = outcome_from_checks(checks, found=True)
        return self._respond(
            started, outcome=outcome,
            summary=DemoPolicyProvider._summary(outcome, "provider", record["name"], checks),
            checks=checks, reference_id=record.get("registration") or record["name"],
            raw={"record": record, "found": True},
        )


class DemoInvoiceProvider(_DemoBase):
    key = "demo_invoice"
    label = "Demo Verification Provider - Invoice / Billing Registry"
    request_types = ("invoice_lookup",)
    description = ("Confirms an invoice reference exists at the issuing provider and that the "
                   "amount, date and patient on the document match the issuer's record.")

    def verify(self, query: VerificationQuery) -> VerificationResponse:
        started = time.perf_counter()
        invoice_number = query.payload.get("invoice_number")
        record = INVOICES.get(normalize_key(invoice_number))
        if not record:
            return self._not_found(started, "invoice", str(invoice_number))

        checks = [VerificationCheck("invoice_found", "Invoice found", str(invoice_number),
                                    record["invoice_number"], True)]
        total = query.payload.get("total")
        if total is not None:
            ok, note = _money_match(total, record["total"])
            checks.append(VerificationCheck(
                "amount_match", "Amount matches issuer record",
                f"{record['total']} {record['currency']}", str(total), ok,
                note + (f" {record.get('note', '')}" if ok is False else ""),
            ))
        issued = query.payload.get("invoice_date")
        if issued:
            parsed = parse_date(str(issued))
            checks.append(VerificationCheck(
                "date_match", "Issue date matches", record["issued_on"],
                parsed.isoformat() if parsed else str(issued),
                bool(parsed and parsed.isoformat() == record["issued_on"]),
            ))
        patient = query.payload.get("patient_name")
        if patient:
            ok, score = _name_match(patient, record.get("patient_name"))
            checks.append(VerificationCheck(
                "patient_match", "Patient matches issuer record", record.get("patient_name"),
                patient, ok, f"Name similarity {score:.2f}." if score is not None else "",
            ))
        outcome = outcome_from_checks(checks, found=True)
        return self._respond(
            started, outcome=outcome,
            summary=DemoPolicyProvider._summary(
                outcome, "invoice", record["invoice_number"], checks),
            checks=checks, reference_id=record["invoice_number"],
            raw={"record": record, "found": True},
        )


class DemoGovIdProvider(_DemoBase):
    key = "demo_gov_id"
    label = "Demo Verification Provider - Government ID Registry"
    request_types = ("identity_lookup",)
    description = ("Confirms an identity document number is on record, valid, and issued to the "
                   "named holder with the stated date of birth.")

    def verify(self, query: VerificationQuery) -> VerificationResponse:
        started = time.perf_counter()
        number = query.payload.get("national_id") or query.payload.get("document_number")
        record = GOV_IDS.get(normalize_key(number))
        if not record:
            return self._not_found(started, "identity document", str(number))

        checks = [
            VerificationCheck("document_exists", "Document on record", str(number),
                              record["document_number"], True),
            VerificationCheck("document_valid", "Document status valid", "valid",
                              record["status"], record["status"] == "valid",
                              record.get("note", "")),
        ]
        name = query.payload.get("customer_name") or query.payload.get("full_name")
        if name:
            ok, score = _name_match(name, record["full_name"])
            checks.append(VerificationCheck(
                "holder_match", "Holder name matches", record["full_name"], name, ok,
                f"Name similarity {score:.2f}." if score is not None else "",
            ))
        dob = query.payload.get("date_of_birth")
        if dob:
            parsed = parse_date(str(dob))
            checks.append(VerificationCheck(
                "dob_match", "Date of birth matches", record["date_of_birth"],
                parsed.isoformat() if parsed else str(dob),
                bool(parsed and parsed.isoformat() == record["date_of_birth"]),
            ))
        expiry = parse_date(record["expiry_date"])
        reference = parse_date(str(query.payload.get("service_date") or "")) or date.today()
        checks.append(VerificationCheck(
            "not_expired", "Document valid at event date", record["expiry_date"],
            reference.isoformat(), bool(expiry and expiry >= reference),
        ))
        outcome = outcome_from_checks(checks, found=True)
        return self._respond(
            started, outcome=outcome,
            summary=DemoPolicyProvider._summary(
                outcome, "identity document", record["document_number"], checks),
            checks=checks, reference_id=record["document_number"],
            raw={"record": record, "found": True},
        )


class DemoVehicleProvider(_DemoBase):
    key = "demo_vehicle"
    label = "Demo Verification Provider - Vehicle Registry"
    request_types = ("vehicle_lookup",)
    description = ("Confirms a registration/VIN pair, the registered keeper, and any write-off "
                   "marker held against the vehicle.")

    def verify(self, query: VerificationQuery) -> VerificationResponse:
        started = time.perf_counter()
        plate = query.payload.get("vehicle_registration")
        record = VEHICLES.get(normalize_key(plate))
        if not record:
            for value in VEHICLES.values():
                if normalize_key(query.payload.get("vin")) == normalize_key(value["vin"]):
                    record = value
                    break
        if not record:
            return self._not_found(started, "vehicle", str(plate))

        checks = [
            VerificationCheck("vehicle_exists", "Vehicle on record", str(plate),
                              record["registration"], True),
            VerificationCheck("registration_status", "Registration active", "registered",
                              record["status"], record["status"] == "registered"),
        ]
        vin = query.payload.get("vin")
        if vin:
            checks.append(VerificationCheck(
                "vin_match", "VIN matches registration", record["vin"], str(vin),
                normalize_key(vin) == normalize_key(record["vin"]),
            ))
        keeper = query.payload.get("customer_name")
        if keeper:
            ok, score = _name_match(keeper, record["registered_keeper"])
            checks.append(VerificationCheck(
                "keeper_match", "Registered keeper matches", record["registered_keeper"],
                keeper, ok, f"Name similarity {score:.2f}." if score is not None else "",
            ))
        marker = record.get("write_off_marker")
        checks.append(VerificationCheck(
            "no_write_off_marker", "No write-off marker on record", "none",
            marker or "none", marker is None,
            record.get("note", "") if marker else "",
        ))
        outcome = outcome_from_checks(checks, found=True)
        return self._respond(
            started, outcome=outcome,
            summary=DemoPolicyProvider._summary(
                outcome, "vehicle", record["registration"], checks),
            checks=checks, reference_id=record["registration"],
            raw={"record": record, "found": True},
        )


class DemoPaymentProvider(_DemoBase):
    key = "demo_payment"
    label = "Demo Verification Provider - Payment / Settlement Registry"
    request_types = ("payment_lookup",)
    description = "Confirms that a settlement reference exists and was actually settled."

    def verify(self, query: VerificationQuery) -> VerificationResponse:
        started = time.perf_counter()
        reference = query.payload.get("transaction_reference")
        record = PAYMENTS.get(normalize_key(reference))
        if not record:
            return self._not_found(started, "payment", str(reference))
        checks = [
            VerificationCheck("payment_found", "Payment reference found", str(reference),
                              record["reference"], True),
            VerificationCheck("payment_settled", "Payment settled", "settled", record["status"],
                              record["status"] == "settled", record.get("note", "")),
        ]
        amount = query.payload.get("amount_paid") or query.payload.get("total")
        if amount is not None:
            ok, note = _money_match(amount, record["amount"])
            checks.append(VerificationCheck(
                "amount_match", "Settled amount matches document",
                f"{record['amount']} {record['currency']}", str(amount), ok, note,
            ))
        outcome = outcome_from_checks(checks, found=True)
        return self._respond(
            started, outcome=outcome,
            summary=DemoPolicyProvider._summary(outcome, "payment", record["reference"], checks),
            checks=checks, reference_id=record["reference"],
            raw={"record": record, "found": True},
        )

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.services.verification.base import VerificationProvider
from app.services.verification.demo_providers import (
    DemoGovIdProvider,
    DemoHospitalProvider,
    DemoInvoiceProvider,
    DemoPaymentProvider,
    DemoPolicyProvider,
    DemoVehicleProvider,
)
from app.services.verification.remote_http import RemoteHttpVerificationProvider

logger = get_logger(__name__)

DEMO_PROVIDERS: dict[str, type[VerificationProvider]] = {
    "demo_policy": DemoPolicyProvider,
    "demo_hospital": DemoHospitalProvider,
    "demo_invoice": DemoInvoiceProvider,
    "demo_gov_id": DemoGovIdProvider,
    "demo_vehicle": DemoVehicleProvider,
    "demo_payment": DemoPaymentProvider,
}

# Which provider answers which request type, per mode.
REQUEST_TYPE_ROUTING: dict[str, str] = {
    "policy_lookup": "demo_policy",
    "provider_lookup": "demo_hospital",
    "invoice_lookup": "demo_invoice",
    "identity_lookup": "demo_gov_id",
    "vehicle_lookup": "demo_vehicle",
    "payment_lookup": "demo_payment",
}


def get_verification_provider(request_type: str) -> VerificationProvider:
    """Route a request type to a provider, honouring the configured mode."""
    if settings.verification_provider == "remote_http":
        remote = RemoteHttpVerificationProvider()
        ok, detail = remote.available()
        if ok:
            return remote
        logger.warning("verification_remote_unavailable_using_demo", extra={"detail": detail})
    key = REQUEST_TYPE_ROUTING.get(request_type)
    if not key:
        raise KeyError(f"No verification provider handles request type '{request_type}'")
    return DEMO_PROVIDERS[key]()


def get_provider_by_key(key: str) -> VerificationProvider:
    if key == "remote_http":
        return RemoteHttpVerificationProvider()
    return DEMO_PROVIDERS[key]()


def list_verification_providers() -> list[dict]:
    providers = [cls().describe() for cls in DEMO_PROVIDERS.values()]
    providers.append(RemoteHttpVerificationProvider().describe())
    return providers


# Which verification requests make sense for each document type, and which
# extracted fields feed them.
PLAN_BY_DOCUMENT_TYPE: dict[str, list[str]] = {
    "medical_invoice": ["policy_lookup", "provider_lookup", "invoice_lookup"],
    "hospital_bill": ["policy_lookup", "provider_lookup", "invoice_lookup"],
    "prescription": ["provider_lookup"],
    "identity_document": ["identity_lookup"],
    "insurance_certificate": ["policy_lookup"],
    "claim_form": ["policy_lookup", "identity_lookup"],
    "vehicle_document": ["vehicle_lookup"],
    "repair_estimate": ["vehicle_lookup", "policy_lookup"],
    "receipt": ["invoice_lookup", "payment_lookup"],
    "police_report": ["vehicle_lookup"],
    "bank_payment_document": ["payment_lookup"],
    "other": [],
}

REQUEST_PAYLOAD_FIELDS: dict[str, tuple[str, ...]] = {
    "policy_lookup": ("policy_number", "customer_name", "patient_name", "insured_name",
                      "date_of_birth", "treatment_date", "total"),
    "provider_lookup": ("hospital_name", "garage_name", "provider_registration",
                        "invoice_number"),
    "invoice_lookup": ("invoice_number", "total", "invoice_date", "patient_name"),
    "identity_lookup": ("national_id", "customer_name", "date_of_birth", "expiry_date"),
    "vehicle_lookup": ("vehicle_registration", "vin", "customer_name"),
    "payment_lookup": ("transaction_reference", "amount_paid", "total"),
}

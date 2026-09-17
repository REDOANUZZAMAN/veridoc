"""Test harness.

The test suite runs against a *real* PostgreSQL database (``veridoc_test``) and
real storage, because most of what is worth testing here - schema constraints,
the audit hash chain, the analysis pipeline - is not meaningful against mocks.
Only external providers are substituted.
"""
from __future__ import annotations

import os
import tempfile
import uuid

# Environment must be set before any app module reads settings.
_TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://veridoc:veridoc@localhost:55432/veridoc_test",
)
os.environ["DATABASE_URL"] = _TEST_DB
os.environ["APP_ENV"] = "test"
os.environ["QUEUE_MODE"] = "inline"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["STORAGE_LOCAL_ROOT"] = tempfile.mkdtemp(prefix="veridoc-test-storage-")
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["RATE_LIMIT_DEFAULT"] = "100000/minute"
os.environ["RATE_LIMIT_LOGIN"] = "100000/minute"
os.environ["RATE_LIMIT_UPLOAD"] = "100000/minute"
os.environ["SEED_PASSWORD"] = "Demo!2026"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine.url import make_url  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402


def _ensure_database() -> None:
    url = make_url(settings.database_url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def database():
    _ensure_database()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(bind=engine)
    from app.db.seed import seed_reference

    with SessionLocal() as db:
        seed_reference(db)
        db.commit()
    yield
    engine.dispose()


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture()
def client(app, database):
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, email: str, password: str = "Demo!2026") -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def admin_token(client):
    return login(client, "admin@veridoc.example")["access_token"]


@pytest.fixture()
def investigator_token(client):
    return login(client, "investigator@veridoc.example")["access_token"]


@pytest.fixture()
def claims_token(client):
    return login(client, "claims@veridoc.example")["access_token"]


@pytest.fixture()
def reviewer_token(client):
    return login(client, "reviewer@veridoc.example")["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def make_claim(client, claims_token):
    def _make(**overrides):
        payload = {
            "customer_name": "Amelia R. Okonkwo",
            "policy_number": "POL-938472",
            "claim_type": "health",
            "customer_dob": "1986-04-12",
            "claimed_amount": "4820.00",
            "currency": "USD",
            "incident_date": "2026-08-15",
            "claim_number": f"CLM-TEST-{uuid.uuid4().hex[:8].upper()}",
            **overrides,
        }
        response = client.post("/api/claims", json=payload, headers=auth(claims_token))
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture()
def invoice_pdf():
    """A small, clean, single-page medical invoice."""
    from app.db.demo_documents import DocSpec, render

    spec = DocSpec(
        key="test-invoice", kind="pdf", title="Medical Invoice",
        organisation="Meridian General Hospital",
        org_subtitle="Ashford NHS Foundation Trust - Provider registration HRG-114-882",
        party_fields=[("Patient name", "Amelia R. Okonkwo"),
                      ("Date of birth", "1986-04-12"),
                      ("Policy number", "POL-938472")],
        header_fields=[("Invoice number", "MGH-2026-004417"),
                       ("Invoice date", "2026-08-18"),
                       ("Treatment date", "2026-08-15"),
                       ("Currency", "USD")],
        items=[("Consultation", "1", "2,450.00", "2,450.00"),
               ("Radiography", "2", "790.00", "1,580.00"),
               ("Cast application", "1", "790.00", "790.00")],
        totals=[("Subtotal", "$4,820.00"), ("Tax", "$0.00"), ("Total amount", "$4,820.00")],
        footer="Payment due within 30 days.", seed=4242,
    )
    data, extension, mime = render(spec)
    return data, mime


@pytest.fixture()
def tampered_invoice_pdf():
    """The same invoice with the total re-set in another typeface and overlaid."""
    from app.db.demo_documents import DocSpec, render

    spec = DocSpec(
        key="test-tampered", kind="pdf", title="Medical Invoice",
        organisation="Meridian General Hospital",
        org_subtitle="Ashford NHS Foundation Trust - Provider registration HRG-114-882",
        party_fields=[("Patient name", "Amelia R. Okonkwo"),
                      ("Date of birth", "1986-04-12"),
                      ("Policy number", "POL-938472")],
        header_fields=[("Invoice number", "MGH-2026-004918"),
                       ("Invoice date", "2026-08-27"),
                       ("Treatment date", "2026-08-24"),
                       ("Currency", "USD")],
        items=[("Theatre time", "1", "2,400.00", "2,400.00"),
               ("Surgeon fee", "1", "1,850.00", "1,850.00"),
               ("Anaesthetist fee", "1", "1,250.00", "1,250.00"),
               ("Recovery ward", "1", "1,000.00", "1,000.00")],
        totals=[("Subtotal", "$6,500.00"), ("Tax", "$0.00"), ("Total amount", "$8,500.00")],
        font_anomaly_field="Total amount", baseline_shift_field="Total amount",
        annotation_overlay=("Total amount", "$8,500.00"),
        producer="Adobe Photoshop 25.3 (Windows)", creator="Microsoft Word",
        seed=4243,
    )
    data, extension, mime = render(spec)
    return data, mime


def upload(client, token, data: bytes, filename: str, mime: str, claim_id: str | None = None,
           analyze: bool = True):
    files = {"file": (filename, data, mime)}
    form = {"analyze": str(analyze).lower()}
    if claim_id:
        form["claim_id"] = claim_id
    return client.post("/api/documents", files=files, data=form, headers=auth(token))

"""Import every model so SQLAlchemy's metadata (and Alembic) sees all tables."""
from app.db.base import Base
from app.db.models.analysis import AnalysisRun, RiskAssessment
from app.db.models.audit import AuditLog
from app.db.models.claim import Claim
from app.db.models.config import DetectionRule, ProviderConfig, SystemSetting
from app.db.models.document import (
    Document,
    DocumentMetadataEntry,
    DocumentPage,
    ExtractedField,
    OcrResult,
)
from app.db.models.findings import (
    FINDING_TABLES,
    AigcFinding,
    ConsistencyFinding,
    CrossDocumentFinding,
    ForensicFinding,
    TamperingFinding,
)
from app.db.models.investigation import (
    Investigation,
    InvestigationNote,
    ReviewActionRecord,
)
from app.db.models.report import Report
from app.db.models.user import RoleDefinition, User
from app.db.models.verification import VerificationRequest, VerificationResult

__all__ = [
    "Base", "AnalysisRun", "RiskAssessment", "AuditLog", "Claim", "DetectionRule",
    "ProviderConfig", "SystemSetting", "Document", "DocumentMetadataEntry", "DocumentPage",
    "ExtractedField", "OcrResult", "FINDING_TABLES", "AigcFinding", "ConsistencyFinding",
    "CrossDocumentFinding", "ForensicFinding", "TamperingFinding", "Investigation",
    "InvestigationNote", "ReviewActionRecord", "Report", "RoleDefinition", "User",
    "VerificationRequest", "VerificationResult",
]

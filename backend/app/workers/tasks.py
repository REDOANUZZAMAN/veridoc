"""Worker entry points.

Each task owns its own database session so it is safe to run in an RQ worker
process, in a FastAPI background task, or synchronously from a test.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.enums import ProcessingStatus
from app.db.session import session_scope

logger = get_logger(__name__)


def analyze_document_task(
    document_id: str, actor_id: str | None = None, run_id: str | None = None,
    reprocess_of: str | None = None,
) -> dict:
    from app.db.models.user import User
    from app.services.pipeline import run_analysis

    with session_scope() as db:
        actor = db.get(User, actor_id) if actor_id else None
        try:
            run = run_analysis(db, document_id, actor=actor, run_id=run_id,
                               reprocess_of=reprocess_of)
            return {"analysis_run_id": run.id, "status": run.status,
                    "findings": run.findings_count}
        except Exception as exc:
            logger.exception("analysis_task_failed", extra={"document_id": document_id})
            # The document itself is never lost; only the run is marked failed.
            from app.db.models.analysis import AnalysisRun
            from app.db.models.document import Document

            if run_id:
                run = db.get(AnalysisRun, run_id)
                if run:
                    run.status = ProcessingStatus.FAILED
                    run.error = f"{type(exc).__name__}: {str(exc)[:400]}"
            doc = db.get(Document, document_id)
            if doc:
                doc.processing_status = ProcessingStatus.FAILED
                doc.processing_message = (
                    "Analysis failed unexpectedly. The original document is preserved and can be "
                    "reprocessed once the cause is resolved."
                )
            return {"status": ProcessingStatus.FAILED, "error": str(exc)[:400]}


def purge_expired_documents_task(dry_run: bool = True) -> dict:
    """Retention enforcement: delete derived artifacts past the retention window.

    Originals are only removed when ``dry_run`` is False *and* the document is
    soft-deleted, so evidence is never silently destroyed by a scheduled job.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.db.models.document import Document
    from app.services.storage.factory import get_storage

    storage = get_storage()
    removed, inspected = [], 0
    with session_scope() as db:
        rows = db.execute(
            select(Document).where(
                Document.retention_expires_at.is_not(None),
                Document.retention_expires_at < datetime.now(timezone.utc),
            )
        ).scalars().all()
        for doc in rows:
            inspected += 1
            entry = {"document_ref": doc.document_ref,
                     "expired_at": doc.retention_expires_at.isoformat(),
                     "artifacts_removed": False, "original_removed": False}
            if not dry_run:
                if hasattr(storage, "delete_prefix"):
                    storage.delete_prefix("artifacts", doc.artifact_prefix)
                    entry["artifacts_removed"] = True
                if doc.deleted_at is not None:
                    storage.delete("originals", doc.storage_key)
                    entry["original_removed"] = True
            removed.append(entry)
    return {"inspected": inspected, "dry_run": dry_run, "documents": removed}

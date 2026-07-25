"""DocumentVerifier — بخش [5] pipeline در سند معماری.

برای هر credential الزامیِ Policy، آخرین Credential ثبت‌شده‌ی provider را
با استفاده از VisionProvider تحلیل می‌کند و نتیجه‌ی ساخت‌یافته (نوع مدرک،
تاریخ انقضا، confidence) را برمی‌گرداند. این ماژول خودش تصمیم eligible/not
نمی‌گیرد — فقط «واقعیت را می‌خواند»؛ تصمیم در policy_engine گرفته می‌شود.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Credential
from app.vision_provider import VisionProvider


@dataclass
class DocumentCheckResult:
    credential_type: str
    present: bool
    expiry_date: datetime | None = None
    days_until_expiry: int | None = None
    extraction_confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


def check_documents(
    db: Session,
    provider_id: str,
    required_types: list[str],
    vision: VisionProvider,
) -> dict[str, DocumentCheckResult]:
    results: dict[str, DocumentCheckResult] = {}

    for cred_type in required_types:
        latest = (
            db.query(Credential)
            .filter(Credential.provider_id == provider_id, Credential.credential_type == cred_type)
            .order_by(Credential.uploaded_at.desc())
            .first()
        )
        if latest is None:
            results[cred_type] = DocumentCheckResult(
                credential_type=cred_type, present=False, notes=["credential_not_uploaded"]
            )
            continue

        # اگر قبلاً استخراج نشده (raw_extraction خالی)، همین حالا با vision provider تحلیل کن.
        if not latest.raw_extraction:
            analysis = vision.analyze_document(Path(latest.evidence_asset.file_path), cred_type)
            latest.extracted_expiry_date = analysis.expiry_date
            latest.extraction_confidence = analysis.confidence
            latest.raw_extraction = {
                "doc_type_guess": analysis.doc_type_guess,
                "notes": analysis.notes,
            }
            db.commit()

        expiry = latest.extracted_expiry_date
        days_left = None
        if expiry is not None:
            now = datetime.now(timezone.utc)
            expiry_aware = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
            days_left = (expiry_aware - now).days

        results[cred_type] = DocumentCheckResult(
            credential_type=cred_type,
            present=True,
            expiry_date=expiry,
            days_until_expiry=days_left,
            extraction_confidence=latest.extraction_confidence,
            notes=list((latest.raw_extraction or {}).get("notes", [])),
        )

    return results

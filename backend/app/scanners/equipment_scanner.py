"""EquipmentVerifier — بخش [5] pipeline در سند معماری.

آخرین عکس تجهیزات provider را با VisionProvider تحلیل می‌کند و برای هر
label الزامی Policy یک confidence برمی‌گرداند.
"""
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import EvidenceAsset
from app.vision_provider import VisionProvider


@dataclass
class EquipmentCheckResult:
    label: str
    detected: bool
    confidence: float


def check_equipment(
    db: Session,
    provider_id: str,
    required_labels: list[dict],
    vision: VisionProvider,
) -> dict[str, EquipmentCheckResult]:
    latest_photo = (
        db.query(EvidenceAsset)
        .filter(EvidenceAsset.provider_id == provider_id, EvidenceAsset.kind == "equipment_photo")
        .order_by(EvidenceAsset.uploaded_at.desc())
        .first()
    )

    labels = [item["type"] for item in required_labels]
    if latest_photo is None:
        return {
            item["type"]: EquipmentCheckResult(label=item["type"], detected=False, confidence=0.0)
            for item in required_labels
        }

    scores = vision.analyze_equipment(Path(latest_photo.file_path), labels)

    results: dict[str, EquipmentCheckResult] = {}
    for item in required_labels:
        label = item["type"]
        min_conf = item.get("min_confidence", 0.7)
        score = float(scores.get(label, 0.0))
        results[label] = EquipmentCheckResult(label=label, detected=bool(score >= min_conf), confidence=score)
    return results

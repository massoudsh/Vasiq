"""RiskScorer — بخش ۶ سند معماری.

خروجی یک عدد ۰ (بی‌ریسک) تا ۱۰۰ (پرریسک) است. منطق وزن‌دهی از policy_engine
مستقل است تا مستقل قابل تست باشد؛ policy فقط سقف مجاز را روی این عدد تعریف می‌کند.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import RiskEvent

_SEVERITY_WEIGHT = {1: 4, 2: 8, 3: 15, 4: 25, 5: 40}
_HALF_LIFE_DAYS = 30  # اثر هر RiskEvent هر ۳۰ روز نصف می‌شود (decay)


@dataclass
class RiskScoreResult:
    score: float
    contributors: list[str] = field(default_factory=list)


def _decayed_weight(event: RiskEvent, now: datetime) -> float:
    occurred = event.occurred_at if event.occurred_at.tzinfo else event.occurred_at.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - occurred).days)
    decay = 0.5 ** (age_days / _HALF_LIFE_DAYS)
    return _SEVERITY_WEIGHT.get(event.severity, 5) * decay


def score_provider(
    db: Session,
    provider_id: str,
    duplicate_photo_detected: bool = False,
    low_confidence_extractions: int = 0,
) -> RiskScoreResult:
    now = datetime.now(timezone.utc)
    events = db.query(RiskEvent).filter(RiskEvent.provider_id == provider_id).all()

    score = 0.0
    contributors: list[str] = []

    for event in events:
        w = _decayed_weight(event, now)
        if w >= 0.5:
            score += w
            contributors.append(f"risk_event:{event.event_type}(severity={event.severity},weight={w:.1f})")

    if duplicate_photo_detected:
        score += 30
        contributors.append("duplicate_evidence_photo_detected(+30)")

    if low_confidence_extractions:
        added = min(low_confidence_extractions * 5, 20)
        score += added
        contributors.append(f"low_confidence_document_extraction(+{added})")

    score = min(100.0, round(score, 1))
    return RiskScoreResult(score=score, contributors=contributors)

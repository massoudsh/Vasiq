"""Orchestrator اصلی — کل pipeline بخش ۳ سند معماری را اجرا می‌کند.

[1] ingest → [2] resolve policy → [3] load provider state → [4] freshness gate
→ [5] run verifiers → [6] policy evaluation → [7] decision → [8] persist/audit
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AuditLog,
    Credential,
    EligibilityDecision,
    EvidenceAsset,
    Policy,
    Provider,
    RiskEvent,
)
from app.policy_engine import evaluate_policy
from app.scanners.document_scanner import check_documents
from app.scanners.duplicate_detector import find_duplicates
from app.scanners.equipment_scanner import check_equipment
from app.scanners.risk_scorer import score_provider
from app.vision_provider import get_vision_provider


class PolicyNotFoundError(Exception):
    pass


class ProviderNotFoundError(Exception):
    pass


@dataclass
class EligibilityResult:
    decision_id: str
    status: str
    risk_score: float
    reasons: list[str]
    valid_until: datetime
    cache_hit: bool = False


def _get_active_policy(db: Session, service_type_code: str) -> Policy:
    policy = (
        db.query(Policy)
        .filter(Policy.service_type_code == service_type_code, Policy.is_active == 1)
        .order_by(Policy.created_at.desc())
        .first()
    )
    if policy is None:
        raise PolicyNotFoundError(f"no active policy for service_type={service_type_code!r}")
    return policy


def _latest_signal_at(db: Session, provider_id: str) -> datetime:
    """آخرین زمانی که یک سیگنال جدید (مدرک/ریسک) برای این provider ثبت شده — برای freshness gate."""
    latest_cred = (
        db.query(Credential.uploaded_at)
        .filter(Credential.provider_id == provider_id)
        .order_by(Credential.uploaded_at.desc())
        .first()
    )
    latest_risk = (
        db.query(RiskEvent.occurred_at)
        .filter(RiskEvent.provider_id == provider_id)
        .order_by(RiskEvent.occurred_at.desc())
        .first()
    )
    candidates = [c[0] for c in (latest_cred, latest_risk) if c]
    if not candidates:
        return datetime.min.replace(tzinfo=timezone.utc)
    return max(c if c.tzinfo else c.replace(tzinfo=timezone.utc) for c in candidates)


def _find_cached_decision(db: Session, provider_id: str, service_type_code: str) -> EligibilityDecision | None:
    now = datetime.now(timezone.utc)
    latest_signal = _latest_signal_at(db, provider_id)

    decision = (
        db.query(EligibilityDecision)
        .filter(
            EligibilityDecision.provider_id == provider_id,
            EligibilityDecision.service_type_code == service_type_code,
            EligibilityDecision.valid_until > now,
        )
        .order_by(EligibilityDecision.created_at.desc())
        .first()
    )
    if decision is None:
        return None

    created_at = decision.created_at if decision.created_at.tzinfo else decision.created_at.replace(tzinfo=timezone.utc)
    if latest_signal > created_at:
        return None  # سیگنال جدید آمده → cache نامعتبر است
    return decision


def check_eligibility(db: Session, provider_id: str, service_type_code: str) -> EligibilityResult:
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if provider is None:
        raise ProviderNotFoundError(f"provider {provider_id!r} not found")

    policy_row = _get_active_policy(db, service_type_code)
    policy = policy_row.body

    # [4] Freshness gate
    cached = _find_cached_decision(db, provider_id, service_type_code)
    if cached is not None:
        return EligibilityResult(
            decision_id=cached.id,
            status=cached.status.value,
            risk_score=cached.risk_score,
            reasons=cached.reasons,
            valid_until=cached.valid_until,
            cache_hit=True,
        )

    # [5] Run verifiers
    vision = get_vision_provider()
    required_cred_types = [c["type"] for c in policy.get("required_credentials", [])]
    document_results = check_documents(db, provider_id, required_cred_types, vision)
    equipment_results = check_equipment(db, provider_id, policy.get("required_equipment", []), vision)

    duplicate_detected = False
    latest_photo = (
        db.query(EvidenceAsset)
        .filter(EvidenceAsset.provider_id == provider_id, EvidenceAsset.kind == "equipment_photo")
        .order_by(EvidenceAsset.uploaded_at.desc())
        .first()
    )
    if latest_photo is not None and latest_photo.phash:
        if policy.get("duplicate_photo_policy", "reject") != "ignore":
            duplicates = find_duplicates(db, latest_photo.phash, exclude_provider_id=provider_id)
            duplicate_detected = len(duplicates) > 0

    low_confidence_count = sum(
        1 for r in document_results.values() if r.present and r.extraction_confidence < 0.5
    )
    risk_result = score_provider(
        db,
        provider_id,
        duplicate_photo_detected=duplicate_detected,
        low_confidence_extractions=low_confidence_count,
    )

    # [6] Policy evaluation
    policy_decision = evaluate_policy(policy, document_results, equipment_results, risk_result.score)

    reasons = list(policy_decision.reasons)
    if duplicate_detected:
        reasons.append("evidence.equipment_photo: matches a photo already used by another provider (possible reuse)")
    reasons.extend(risk_result.contributors)

    # [7] Decision
    valid_until = datetime.now(timezone.utc) + timedelta(hours=settings.default_decision_ttl_hours)
    verifier_snapshot = {
        "documents": {k: vars(v) for k, v in document_results.items()},
        "equipment": {k: vars(v) for k, v in equipment_results.items()},
        "duplicate_detected": duplicate_detected,
        "risk_contributors": risk_result.contributors,
    }

    decision = EligibilityDecision(
        provider_id=provider_id,
        service_type_code=service_type_code,
        policy_version=policy_row.version,
        status=policy_decision.status,
        risk_score=risk_result.score,
        reasons=reasons,
        verifier_results=_json_safe(verifier_snapshot),
        valid_until=valid_until,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)

    # [8] Audit (append-only)
    audit = AuditLog(
        decision_id=decision.id,
        provider_id=provider_id,
        service_type_code=service_type_code,
        status=decision.status.value,
        snapshot=_json_safe(verifier_snapshot),
    )
    db.add(audit)
    db.commit()

    return EligibilityResult(
        decision_id=decision.id,
        status=decision.status.value,
        risk_score=decision.risk_score,
        reasons=decision.reasons,
        valid_until=decision.valid_until,
        cache_hit=False,
    )


def _json_safe(obj):
    """dataclassها/datetimeها را برای ذخیره در ستون JSON قابل‌سریالایز می‌کند."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj

"""تست‌های خالص Policy Engine — بدون DB/AI (بخش ۴ سند معماری)."""
from app.models import DecisionStatus
from app.policy_engine import evaluate_policy
from app.scanners.document_scanner import DocumentCheckResult
from app.scanners.equipment_scanner import EquipmentCheckResult

BASE_POLICY = {
    "required_credentials": [
        {"type": "license", "min_days_valid": 30, "grace_days": 3},
    ],
    "required_equipment": [
        {"type": "box", "min_confidence": 0.75},
    ],
    "risk": {"max_score": 65, "conditional_band": [50, 65]},
}


def _doc(present=True, days=60, confidence=0.9):
    return DocumentCheckResult(
        credential_type="license",
        present=present,
        days_until_expiry=days if present else None,
        extraction_confidence=confidence,
    )


def _equip(detected=True, confidence=0.9):
    return EquipmentCheckResult(label="box", detected=detected, confidence=confidence)


def test_all_pass_is_eligible():
    decision = evaluate_policy(
        BASE_POLICY, {"license": _doc(days=60)}, {"box": _equip(True)}, risk_score=10
    )
    assert decision.status == DecisionStatus.eligible


def test_missing_credential_is_not_eligible():
    decision = evaluate_policy(
        BASE_POLICY, {"license": _doc(present=False)}, {"box": _equip(True)}, risk_score=10
    )
    assert decision.status == DecisionStatus.not_eligible
    assert any("missing" in r for r in decision.reasons)


def test_expired_credential_is_not_eligible():
    decision = evaluate_policy(
        BASE_POLICY, {"license": _doc(days=-5)}, {"box": _equip(True)}, risk_score=10
    )
    assert decision.status == DecisionStatus.not_eligible
    assert any("expired" in r for r in decision.reasons)


def test_near_expiry_within_grace_is_conditional():
    # min_days_valid=30, grace_days=3 → days_left in [27, 30) باید conditional باشد
    decision = evaluate_policy(
        BASE_POLICY, {"license": _doc(days=28)}, {"box": _equip(True)}, risk_score=10
    )
    assert decision.status == DecisionStatus.conditional


def test_near_expiry_below_grace_is_not_eligible():
    # days_left=20 که از (min_days_valid - grace_days)=27 هم کمتر است
    decision = evaluate_policy(
        BASE_POLICY, {"license": _doc(days=20)}, {"box": _equip(True)}, risk_score=10
    )
    assert decision.status == DecisionStatus.not_eligible


def test_missing_equipment_is_not_eligible():
    decision = evaluate_policy(
        BASE_POLICY, {"license": _doc(days=60)}, {"box": _equip(False, confidence=0.2)}, risk_score=10
    )
    assert decision.status == DecisionStatus.not_eligible
    assert any("equipment.box" in r for r in decision.reasons)


def test_risk_above_max_is_not_eligible():
    decision = evaluate_policy(
        BASE_POLICY, {"license": _doc(days=60)}, {"box": _equip(True)}, risk_score=90
    )
    assert decision.status == DecisionStatus.not_eligible


def test_risk_in_conditional_band():
    decision = evaluate_policy(
        BASE_POLICY, {"license": _doc(days=60)}, {"box": _equip(True)}, risk_score=55
    )
    assert decision.status == DecisionStatus.conditional


def test_unconfirmed_expiry_is_conditional_not_hard_fail():
    doc = DocumentCheckResult(credential_type="license", present=True, days_until_expiry=None)
    decision = evaluate_policy(BASE_POLICY, {"license": doc}, {"box": _equip(True)}, risk_score=10)
    assert decision.status == DecisionStatus.conditional

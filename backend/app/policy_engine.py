"""Policy Engine — بخش ۴ سند معماری.

کاملاً خالص و بدون وابستگی به AI/DB: ورودی = policy dict + خروجی verifierها،
خروجی = تصمیم + دلایل. همین جداسازی یعنی تغییر قوانین کسب‌وکار نیازی به
تغییر مدل یا کد AI ندارد و کاملاً unit-test پذیر است.
"""
from dataclasses import dataclass, field

from app.models import DecisionStatus
from app.scanners.document_scanner import DocumentCheckResult
from app.scanners.equipment_scanner import EquipmentCheckResult


@dataclass
class PolicyDecision:
    status: DecisionStatus
    reasons: list[str] = field(default_factory=list)


def evaluate_policy(
    policy: dict,
    document_results: dict[str, DocumentCheckResult],
    equipment_results: dict[str, EquipmentCheckResult],
    risk_score: float,
) -> PolicyDecision:
    reasons: list[str] = []
    hard_fail = False
    soft_fail = False  # منجر به conditional می‌شود، نه رد قطعی

    # --- ۱) مدارک الزامی ---
    for req in policy.get("required_credentials", []):
        cred_type = req["type"]
        min_days = req.get("min_days_valid", 0)
        grace_days = req.get("grace_days", 0)
        result = document_results.get(cred_type)

        if result is None or not result.present:
            hard_fail = True
            reasons.append(f"credential.{cred_type}: missing")
            continue

        if result.days_until_expiry is None:
            soft_fail = True
            reasons.append(f"credential.{cred_type}: expiry date not confirmed (needs manual review)")
            continue

        days_left = result.days_until_expiry
        if days_left < 0:
            hard_fail = True
            reasons.append(f"credential.{cred_type}: expired {abs(days_left)} days ago")
        elif days_left < min_days:
            if days_left >= min_days - grace_days:
                soft_fail = True
                reasons.append(
                    f"credential.{cred_type}: valid, expires in {days_left} days (within grace period)"
                )
            else:
                hard_fail = True
                reasons.append(
                    f"credential.{cred_type}: expires in {days_left} days (below required {min_days})"
                )
        else:
            reasons.append(f"credential.{cred_type}: valid, expires in {days_left} days")

    # --- ۲) تجهیزات الزامی ---
    for req in policy.get("required_equipment", []):
        label = req["type"]
        min_conf = req.get("min_confidence", 0.7)
        result = equipment_results.get(label)

        if result is None or not result.detected:
            conf = result.confidence if result else 0.0
            hard_fail = True
            reasons.append(f"equipment.{label}: NOT detected (confidence {conf:.2f} < {min_conf})")
        else:
            reasons.append(f"equipment.{label}: detected (confidence {result.confidence:.2f})")

    # --- ۳) ریسک ---
    risk_cfg = policy.get("risk", {})
    max_score = risk_cfg.get("max_score", 100)
    conditional_band = risk_cfg.get("conditional_band", [max_score, max_score])

    if risk_score > max_score:
        hard_fail = True
        reasons.append(f"risk_score {risk_score} exceeds max_score {max_score}")
    elif conditional_band[0] <= risk_score <= conditional_band[1]:
        soft_fail = True
        reasons.append(f"risk_score {risk_score} within conditional band {conditional_band}")
    else:
        reasons.append(f"risk_score {risk_score} within acceptable range")

    if hard_fail:
        status = DecisionStatus.not_eligible
    elif soft_fail:
        status = DecisionStatus.conditional
    else:
        status = DecisionStatus.eligible

    return PolicyDecision(status=status, reasons=reasons)

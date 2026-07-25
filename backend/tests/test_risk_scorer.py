from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import RiskEvent
from app.scanners.risk_scorer import score_provider


def test_no_events_zero_score(client):
    db = SessionLocal()
    try:
        result = score_provider(db, "prv_none")
        assert result.score == 0.0
    finally:
        db.close()


def test_recent_severe_event_raises_score(client):
    db = SessionLocal()
    try:
        db.add(RiskEvent(provider_id="prv_x", event_type="safety_report", severity=5))
        db.commit()
        result = score_provider(db, "prv_x")
        assert result.score >= 35
    finally:
        db.close()


def test_old_event_decays(client):
    db = SessionLocal()
    try:
        old = datetime.now(timezone.utc) - timedelta(days=90)
        db.add(RiskEvent(provider_id="prv_old", event_type="complaint", severity=3, occurred_at=old))
        db.commit()
        result = score_provider(db, "prv_old")
        # severity=3 weight=15، بعد از ۹۰ روز (۳ نیم‌عمر) → ~15*0.125 ≈ 1.9
        assert 0 < result.score < 5
    finally:
        db.close()


def test_duplicate_photo_adds_flat_penalty(client):
    db = SessionLocal()
    try:
        result = score_provider(db, "prv_dup", duplicate_photo_detected=True)
        assert result.score == 30.0
    finally:
        db.close()

"""مدل‌های ORM — منبع حقیقت ساختار داده (بخش ۸ سند معماری)."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionStatus(str, enum.Enum):
    eligible = "eligible"
    conditional = "conditional"
    not_eligible = "not_eligible"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("tnt"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ServiceType(Base):
    __tablename__ = "service_types"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("svc"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)  # e.g. food_delivery_bike
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("pol"))
    service_type_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("prv"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    credentials: Mapped[list["Credential"]] = relationship(back_populates="provider")
    risk_events: Mapped[list["RiskEvent"]] = relationship(back_populates="provider")


class EvidenceAsset(Base):
    """هر فایل خام (تصویر مدرک یا عکس تجهیزات) با perceptual hash برای تشخیص تکراری."""

    __tablename__ = "evidence_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("ev"))
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # document | equipment_photo
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    phash: Mapped[str] = mapped_column(String, nullable=True, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("crd"))
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    evidence_asset_id: Mapped[str] = mapped_column(ForeignKey("evidence_assets.id"), nullable=False)
    credential_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. motorcycle_license
    extracted_expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    raw_extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    provider: Mapped[Provider] = relationship(back_populates="credentials")
    evidence_asset: Mapped[EvidenceAsset] = relationship()


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("rev"))
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)  # complaint | cancellation | safety_report
    severity: Mapped[int] = mapped_column(Integer, default=1)  # 1..5
    note: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    provider: Mapped[Provider] = relationship(back_populates="risk_events")


class EligibilityDecision(Base):
    __tablename__ = "eligibility_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("dec"))
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False, index=True)
    service_type_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[DecisionStatus] = mapped_column(Enum(DecisionStatus), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    verifier_results: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(Base):
    """رکورد append-only برای compliance؛ هرگز update/delete نمی‌شود."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _uid("aud"))
    decision_id: Mapped[str] = mapped_column(ForeignKey("eligibility_decisions.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(String, nullable=False)
    service_type_code: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

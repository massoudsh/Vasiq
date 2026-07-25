"""Vasiq API — ورودی سرویس. جزئیات هر endpoint در docs/architecture.md بخش ۷."""
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, init_db
from app.eligibility import PolicyNotFoundError, ProviderNotFoundError, check_eligibility
from app.models import Credential, EligibilityDecision, EvidenceAsset, Policy, Provider, RiskEvent, Tenant
from app.scanners.duplicate_detector import compute_phash
from app.schemas import (
    CredentialOut,
    DecisionHistoryItem,
    EligibilityCheckRequest,
    EligibilityCheckResponse,
    PolicyOut,
    PolicyUpsert,
    ProviderCreate,
    ProviderOut,
    RiskEventCreate,
    TenantCreate,
    TenantOut,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Vasiq — AI Provider Verification & Assignment Eligibility Engine",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------- Tenants --
@app.post("/v1/tenants", response_model=TenantOut)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    tenant = Tenant(name=payload.name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


# --------------------------------------------------------------- Providers --
@app.post("/v1/providers", response_model=ProviderOut)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    provider = Provider(tenant_id=payload.tenant_id, full_name=payload.full_name)
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def _save_upload(file: UploadFile, subdir: str) -> Path:
    target_dir = settings.storage_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix or ".bin"
    dest = target_dir / f"{uuid.uuid4().hex}{ext}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return dest


@app.post("/v1/providers/{provider_id}/credentials", response_model=CredentialOut)
def upload_credential(
    provider_id: str,
    credential_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if provider is None:
        raise HTTPException(404, "provider not found")

    dest = _save_upload(file, "documents")
    phash = None
    try:
        phash = str(compute_phash(dest))
    except Exception:
        pass  # فایل غیرتصویری (مثلاً PDF) — phash اختیاری است

    asset = EvidenceAsset(provider_id=provider_id, kind="document", file_path=str(dest), phash=phash)
    db.add(asset)
    db.commit()
    db.refresh(asset)

    credential = Credential(
        provider_id=provider_id, evidence_asset_id=asset.id, credential_type=credential_type
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return credential


@app.post("/v1/providers/{provider_id}/equipment-photos")
def upload_equipment_photo(provider_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if provider is None:
        raise HTTPException(404, "provider not found")

    dest = _save_upload(file, "equipment")
    phash = str(compute_phash(dest))

    asset = EvidenceAsset(provider_id=provider_id, kind="equipment_photo", file_path=str(dest), phash=phash)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return {"evidence_asset_id": asset.id, "phash": phash}


@app.post("/v1/providers/{provider_id}/risk-events")
def add_risk_event(provider_id: str, payload: RiskEventCreate, db: Session = Depends(get_db)):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if provider is None:
        raise HTTPException(404, "provider not found")

    event = RiskEvent(
        provider_id=provider_id,
        event_type=payload.event_type,
        severity=payload.severity,
        note=payload.note,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": event.id}


@app.get("/v1/providers/{provider_id}/history", response_model=list[DecisionHistoryItem])
def provider_history(provider_id: str, db: Session = Depends(get_db)):
    decisions = (
        db.query(EligibilityDecision)
        .filter(EligibilityDecision.provider_id == provider_id)
        .order_by(EligibilityDecision.created_at.desc())
        .all()
    )
    return decisions


# ----------------------------------------------------------------- Policy --
@app.put("/v1/policies/{service_type_code}", response_model=PolicyOut)
def upsert_policy(service_type_code: str, payload: PolicyUpsert, db: Session = Depends(get_db)):
    if payload.service_type_code != service_type_code:
        raise HTTPException(400, "service_type_code mismatch")

    db.query(Policy).filter(Policy.service_type_code == service_type_code, Policy.is_active == 1).update(
        {"is_active": 0}
    )
    policy = Policy(
        service_type_code=service_type_code, version=payload.version, body=payload.body, is_active=1
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@app.get("/v1/policies/{service_type_code}", response_model=PolicyOut)
def get_policy(service_type_code: str, db: Session = Depends(get_db)):
    policy = (
        db.query(Policy)
        .filter(Policy.service_type_code == service_type_code, Policy.is_active == 1)
        .order_by(Policy.created_at.desc())
        .first()
    )
    if policy is None:
        raise HTTPException(404, "no active policy for this service_type")
    return policy


# ------------------------------------------------------------- Eligibility --
@app.post("/v1/eligibility/check", response_model=EligibilityCheckResponse)
def eligibility_check(payload: EligibilityCheckRequest, db: Session = Depends(get_db)):
    try:
        result = check_eligibility(db, payload.provider_id, payload.service_type_code)
    except ProviderNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PolicyNotFoundError as exc:
        raise HTTPException(422, str(exc)) from exc

    return EligibilityCheckResponse(
        decision_id=result.decision_id,
        status=result.status,
        risk_score=result.risk_score,
        reasons=result.reasons,
        valid_until=result.valid_until,
        cache_hit=result.cache_hit,
    )


@app.get("/v1/eligibility/{decision_id}", response_model=DecisionHistoryItem)
def get_decision(decision_id: str, db: Session = Depends(get_db)):
    decision = db.query(EligibilityDecision).filter(EligibilityDecision.id == decision_id).first()
    if decision is None:
        raise HTTPException(404, "decision not found")
    return decision


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": settings.app_name}

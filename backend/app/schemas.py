from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    name: str


class TenantOut(BaseModel):
    id: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class ProviderCreate(BaseModel):
    tenant_id: str
    full_name: str


class ProviderOut(BaseModel):
    id: str
    tenant_id: str
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class RiskEventCreate(BaseModel):
    event_type: str = Field(description="complaint | cancellation | safety_report")
    severity: int = Field(ge=1, le=5)
    note: str = ""


class PolicyUpsert(BaseModel):
    service_type_code: str
    version: str
    body: dict


class PolicyOut(BaseModel):
    id: str
    service_type_code: str
    version: str
    body: dict
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class EligibilityCheckRequest(BaseModel):
    provider_id: str
    service_type_code: str


class EligibilityCheckResponse(BaseModel):
    decision_id: str
    status: str
    risk_score: float
    reasons: list[str]
    valid_until: datetime
    cache_hit: bool


class CredentialOut(BaseModel):
    id: str
    credential_type: str
    extracted_expiry_date: datetime | None
    extraction_confidence: float

    model_config = ConfigDict(from_attributes=True)


class DecisionHistoryItem(BaseModel):
    id: str
    service_type_code: str
    status: str
    risk_score: float
    reasons: list[str]
    created_at: datetime
    valid_until: datetime

    model_config = ConfigDict(from_attributes=True)

"""تست integration: کل pipeline از طریق HTTP API (بخش ۳ سند معماری)."""
import io

from PIL import Image

from scripts.seed_policies import main as seed_policies


def _image_bytes(color=(200, 200, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (128, 128), color).save(buf, format="PNG")
    return buf.getvalue()


def _make_provider(client):
    tenant = client.post("/v1/tenants", json={"name": "Test Co"}).json()
    provider = client.post(
        "/v1/providers", json={"tenant_id": tenant["id"], "full_name": "Test Provider"}
    ).json()
    return provider["id"]


def test_no_policy_returns_422(client):
    provider_id = _make_provider(client)
    r = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "unknown_service"},
    )
    assert r.status_code == 422


def test_unknown_provider_returns_404(client):
    seed_policies()
    r = client.post(
        "/v1/eligibility/check",
        json={"provider_id": "prv_doesnotexist", "service_type_code": "food_delivery_bike"},
    )
    assert r.status_code == 404


def test_missing_everything_is_not_eligible(client):
    seed_policies()
    provider_id = _make_provider(client)
    r = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_eligible"
    assert any("missing" in reason for reason in body["reasons"])


def test_second_call_is_cache_hit(client):
    seed_policies()
    provider_id = _make_provider(client)
    r1 = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    r2 = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    assert r1.json()["cache_hit"] is False
    assert r2.json()["cache_hit"] is True
    assert r1.json()["decision_id"] == r2.json()["decision_id"]


def test_new_credential_invalidates_cache(client):
    seed_policies()
    provider_id = _make_provider(client)
    client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    client.post(
        f"/v1/providers/{provider_id}/credentials",
        params={"credential_type": "motorcycle_license"},
        files={"file": ("license.png", _image_bytes(), "image/png")},
    )
    r2 = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    assert r2.json()["cache_hit"] is False


def test_duplicate_equipment_photo_raises_risk(client):
    seed_policies()
    provider_a = _make_provider(client)
    provider_b = _make_provider(client)

    shared_photo = _image_bytes((10, 20, 30))
    client.post(
        f"/v1/providers/{provider_a}/equipment-photos",
        files={"file": ("box.png", shared_photo, "image/png")},
    )
    client.post(
        f"/v1/providers/{provider_b}/equipment-photos",
        files={"file": ("box_copy.png", shared_photo, "image/png")},
    )

    r = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_b, "service_type_code": "food_delivery_bike"},
    )
    reasons = r.json()["reasons"]
    assert any("reuse" in reason for reason in reasons)
    assert r.json()["risk_score"] >= 30


def test_risk_event_increases_score(client):
    seed_policies()
    provider_id = _make_provider(client)
    client.post(
        f"/v1/providers/{provider_id}/risk-events",
        json={"event_type": "safety_report", "severity": 5, "note": "reported by customer"},
    )
    r = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    assert r.json()["risk_score"] >= 40


def test_provider_history_lists_decisions(client):
    seed_policies()
    provider_id = _make_provider(client)
    client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    r = client.get(f"/v1/providers/{provider_id}/history")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_policy_upsert_and_get(client):
    body = {
        "service_type_code": "custom_service",
        "version": "v1",
        "body": {
            "service_type": "custom_service",
            "policy_version": "v1",
            "required_credentials": [],
            "required_equipment": [],
            "risk": {"max_score": 50, "conditional_band": [30, 50]},
        },
    }
    r = client.put("/v1/policies/custom_service", json=body)
    assert r.status_code == 200

    r2 = client.get("/v1/policies/custom_service")
    assert r2.status_code == 200
    assert r2.json()["version"] == "v1"

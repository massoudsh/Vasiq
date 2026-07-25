"""دموی end-to-end کل pipeline بدون نیاز به سرور جدا (با TestClient).

سناریو: یک provider برای food_delivery_bike ثبت می‌شود، مدارک و عکس تجهیزات
آپلود می‌کند، و /v1/eligibility/check برای یک assignment واقعی فراخوانی می‌شود.
سپس همان provider یک عکس تجهیزات "کپی‌شده از provider دیگر" آپلود می‌کند تا
duplicate detection را نشان دهد.
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402
from scripts.seed_policies import main as seed_policies  # noqa: E402

client = TestClient(app)


def _image_bytes(color=(200, 200, 200), size=(256, 256)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    seed_policies()

    tenant = client.post("/v1/tenants", json={"name": "Demo Delivery Co"}).json()
    print("tenant:", tenant["id"])

    provider = client.post(
        "/v1/providers", json={"tenant_id": tenant["id"], "full_name": "Ali Rezaei"}
    ).json()
    provider_id = provider["id"]
    print("provider:", provider_id)

    # مدرک ۱: گواهینامه موتور (تصویر ساده — OCR در این محیط ممکن است متن استخراج نکند)
    r = client.post(
        f"/v1/providers/{provider_id}/credentials",
        params={"credential_type": "motorcycle_license"},
        files={"file": ("license.png", _image_bytes((180, 180, 220)), "image/png")},
    )
    print("credential upload:", r.status_code, r.json())

    r = client.post(
        f"/v1/providers/{provider_id}/credentials",
        params={"credential_type": "vehicle_insurance"},
        files={"file": ("insurance.png", _image_bytes((180, 220, 180)), "image/png")},
    )
    print("credential upload:", r.status_code, r.json())

    # عکس تجهیزات: شبیه به مرجع delivery_box (نارنجی، rect) تا شباهت تصویری بالا باشد
    ref_dir = Path(__file__).resolve().parent.parent / "equipment_references"
    box_bytes = (ref_dir / "delivery_box.png").read_bytes()
    r = client.post(
        f"/v1/providers/{provider_id}/equipment-photos",
        files={"file": ("box.png", box_bytes, "image/png")},
    )
    print("equipment photo upload:", r.status_code, r.json())

    print("\n--- eligibility check #1 (full run) ---")
    r = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    print(r.status_code, r.json())

    print("\n--- eligibility check #2 (should be cache_hit) ---")
    r = client.post(
        "/v1/eligibility/check",
        json={"provider_id": provider_id, "service_type_code": "food_delivery_bike"},
    )
    print(r.status_code, r.json())

    # provider دوم که همان عکس تجهیزات را reuse می‌کند → duplicate detection
    provider2 = client.post(
        "/v1/providers", json={"tenant_id": tenant["id"], "full_name": "Second Provider"}
    ).json()
    p2 = provider2["id"]
    client.post(
        f"/v1/providers/{p2}/credentials",
        params={"credential_type": "motorcycle_license"},
        files={"file": ("license.png", _image_bytes((180, 180, 220)), "image/png")},
    )
    client.post(
        f"/v1/providers/{p2}/credentials",
        params={"credential_type": "vehicle_insurance"},
        files={"file": ("insurance.png", _image_bytes((180, 220, 180)), "image/png")},
    )
    client.post(
        f"/v1/providers/{p2}/equipment-photos",
        files={"file": ("box_copied.png", box_bytes, "image/png")},  # همان بایت‌های provider اول
    )

    print("\n--- eligibility check for provider #2 (duplicate photo reused) ---")
    r = client.post(
        "/v1/eligibility/check",
        json={"provider_id": p2, "service_type_code": "food_delivery_bike"},
    )
    print(r.status_code, r.json())

    print("\n--- history for provider #1 ---")
    r = client.get(f"/v1/providers/{provider_id}/history")
    print(r.status_code, r.json())


if __name__ == "__main__":
    main()

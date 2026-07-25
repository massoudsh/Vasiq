"""بارگذاری همه‌ی policyهای backend/policies/*.json در دیتابیس (idempotent-ish: هر بار یک نسخه‌ی جدید فعال می‌کند)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Policy  # noqa: E402

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        for path in sorted(POLICIES_DIR.glob("*.json")):
            body = json.loads(path.read_text(encoding="utf-8"))
            service_type_code = body["service_type"]
            version = body["policy_version"]

            db.query(Policy).filter(
                Policy.service_type_code == service_type_code, Policy.is_active == 1
            ).update({"is_active": 0})

            policy = Policy(
                service_type_code=service_type_code, version=version, body=body, is_active=1
            )
            db.add(policy)
            db.commit()
            print(f"seeded policy: {service_type_code} ({version})")
    finally:
        db.close()


if __name__ == "__main__":
    main()

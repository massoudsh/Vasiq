"""تشخیص عکس تکراری/reuse-شده با perceptual hashing.

یک سیگنال ارزان و مؤثر ضدتقلب: اگر عکسی که برای یک مدرک/تجهیز آپلود شده،
عیناً (یا با تفاوت جزئی فشرده‌سازی) قبلاً برای یک provider دیگر یا در یک
تاریخ خیلی قبل‌تر آپلود شده باشد، به‌جای «صلاحیت واقعی» ممکن است «کپی/reuse»
باشد. این بررسی بدون نیاز به هیچ مدل AI انجام می‌شود.
"""
from pathlib import Path

import imagehash
from PIL import Image
from sqlalchemy.orm import Session

from app.models import EvidenceAsset

DEFAULT_DUPLICATE_THRESHOLD = 6  # hamming distance؛ کمتر یعنی شباهت بیشتر


def compute_phash(image_path: Path) -> imagehash.ImageHash:
    with Image.open(image_path) as img:
        return imagehash.phash(img)


def find_duplicates(
    db: Session,
    phash: str,
    exclude_provider_id: str,
    threshold: int = DEFAULT_DUPLICATE_THRESHOLD,
) -> list[EvidenceAsset]:
    """عکس‌های مشابه که متعلق به providerهای دیگر هستند را برمی‌گرداند."""
    target = imagehash.hex_to_hash(phash)
    matches: list[EvidenceAsset] = []

    assets = (
        db.query(EvidenceAsset)
        .filter(EvidenceAsset.provider_id != exclude_provider_id, EvidenceAsset.phash.isnot(None))
        .all()
    )
    for asset in assets:
        try:
            other = imagehash.hex_to_hash(asset.phash)
        except ValueError:
            continue
        if target - other <= threshold:
            matches.append(asset)
    return matches

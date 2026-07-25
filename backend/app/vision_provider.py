"""لایه‌ی انتزاعی Vision/OCR — بخش ۵ سند معماری.

هدف: تعویض vendor مدل AI بدون تغییر در policy_engine یا eligibility.
`HeuristicVisionProvider` بدون نیاز به هیچ کلید API خارجی کار می‌کند (برای MVP/dev)؛
`ExternalVisionProvider` یک skeleton برای اتصال به یک مدل multimodal واقعی
(OpenAI/Gemini/داخلی) در production است.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageStat

try:
    import pytesseract  # type: ignore

    _HAS_TESSERACT = True
except ImportError:  # pragma: no cover - بسته به محیط استقرار
    _HAS_TESSERACT = False


@dataclass
class DocumentAnalysis:
    doc_type_guess: str | None
    expiry_date: datetime | None
    confidence: float
    raw_text: str = ""
    notes: list[str] = field(default_factory=list)


class VisionProvider(ABC):
    @abstractmethod
    def analyze_document(self, image_path: Path, credential_type: str) -> DocumentAnalysis: ...

    @abstractmethod
    def analyze_equipment(self, image_path: Path, target_labels: list[str]) -> dict[str, float]:
        """برای هر label، یک confidence بین ۰ تا ۱ برمی‌گرداند."""
        ...


# --- استخراج تاریخ از متن OCR (فرمت‌های رایج مدارک ایرانی: yyyy/mm/dd میلادی یا شمسی) ---
_DATE_PATTERNS = [
    r"(?P<y>20\d{2})[/\-.](?P<m>\d{1,2})[/\-.](?P<d>\d{1,2})",
    r"(?P<d>\d{1,2})[/\-.](?P<m>\d{1,2})[/\-.](?P<y>20\d{2})",
]


def _extract_latest_date(text: str) -> datetime | None:
    candidates: list[datetime] = []
    for pattern in _DATE_PATTERNS:
        for m in re.finditer(pattern, text):
            try:
                y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
                if 1 <= mo <= 12 and 1 <= d <= 31:
                    candidates.append(datetime(y, mo, d))
            except ValueError:
                continue
    return max(candidates) if candidates else None


class HeuristicVisionProvider(VisionProvider):
    """
    استخراج مدرک:
      - اگر tesseract روی سرور نصب باشد (`pytesseract`)، از OCR واقعی (فارسی+انگلیسی
        در صورت وجود language pack) برای خواندن متن و استخراج تاریخ انقضا استفاده می‌شود.
      - در غیر این صورت (محیطی بدون tesseract)، confidence پایین برمی‌گردد و
        `needs_manual_review=True` در notes ثبت می‌شود — این یک fallback صادقانه است،
        نه ادعای استخراج موفق.

    تشخیص تجهیزات:
      - چون object detection واقعی نیازمند یک مدل vision آموزش‌دیده است که در این
        MVP آفلاین در دسترس نیست، از تطبیق تشابه تصویری (perceptual hash distance)
        نسبت به عکس‌های مرجع هر label استفاده می‌شود (`equipment_references/`).
        این یک placeholder کاربردی و صادقانه است؛ در production باید با
        `ExternalVisionProvider` (مدل object detection واقعی) جایگزین شود.
    """

    def analyze_document(self, image_path: Path, credential_type: str) -> DocumentAnalysis:
        if not _HAS_TESSERACT:
            return DocumentAnalysis(
                doc_type_guess=credential_type,
                expiry_date=None,
                confidence=0.0,
                notes=["ocr_unavailable: tesseract not installed on this host — needs_manual_review"],
            )

        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang="fas+eng")
        except Exception as exc:  # pragma: no cover
            return DocumentAnalysis(
                doc_type_guess=credential_type,
                expiry_date=None,
                confidence=0.0,
                notes=[f"ocr_error: {exc} — needs_manual_review"],
            )

        expiry = _extract_latest_date(text)
        confidence = 0.85 if expiry else 0.25
        notes = [] if expiry else ["no_date_pattern_found — needs_manual_review"]
        return DocumentAnalysis(
            doc_type_guess=credential_type,
            expiry_date=expiry,
            confidence=confidence,
            raw_text=text[:2000],
            notes=notes,
        )

    def analyze_equipment(self, image_path: Path, target_labels: list[str]) -> dict[str, float]:
        from app.scanners.duplicate_detector import compute_phash  # local import to avoid cycle

        results: dict[str, float] = {}
        try:
            uploaded_hash = compute_phash(image_path)
        except Exception:
            return {label: 0.0 for label in target_labels}

        refs_dir = Path(__file__).resolve().parent.parent / "equipment_references"
        for label in target_labels:
            ref_path = refs_dir / f"{label}.png"
            if not ref_path.exists():
                results[label] = 0.0
                continue
            ref_hash = compute_phash(ref_path)
            distance = int(uploaded_hash - ref_hash)  # hamming distance, 0=identical
            max_distance = 64
            similarity = max(0.0, 1 - (distance / max_distance))
            results[label] = round(float(similarity), 3)

        # سیگنال کمکی: خیلی تیره/محو بودن عکس → confidence همه‌ی labelها را کاهش بده
        try:
            stat = ImageStat.Stat(Image.open(image_path).convert("L"))
            if stat.stddev[0] < 15:  # تصویر کم‌کنتراست/محتمل بی‌کیفیت
                results = {k: round(v * 0.5, 3) for k, v in results.items()}
        except Exception:
            pass

        return results


def get_vision_provider() -> VisionProvider:
    from app.config import settings

    if settings.vision_provider == "heuristic":
        return HeuristicVisionProvider()
    raise NotImplementedError(
        f"vision_provider={settings.vision_provider!r} پیاده‌سازی نشده. "
        "برای production یک ExternalVisionProvider اضافه کنید."
    )

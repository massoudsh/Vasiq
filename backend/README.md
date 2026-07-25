# Vasiq — Backend (MVP)

پیاده‌سازی مرجع بخش ۳ تا ۸ سند معماری (`../docs/architecture.md`). Stack: FastAPI + SQLAlchemy + SQLite (پروتوتایپ) + `imagehash`.

## اجرا

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

مستندات تعاملی API: `http://localhost:8000/docs`

## بارگذاری Policyهای نمونه (۵ vertical)

```bash
python3 scripts/seed_policies.py
```

فایل‌های policy در `policies/*.json` (دلیوری، تاکسی، خدمات منزل، لجستیک، نیروی میدانی).

## دموی end-to-end

یک سناریوی کامل (ثبت provider → آپلود مدرک/عکس تجهیزات → بررسی صلاحیت → cache hit → تشخیص عکس تکراری بین دو provider) را بدون نیاز به اجرای سرور جدا نشان می‌دهد:

```bash
python3 scripts/demo.py
```

## تست‌ها

```bash
pip install pytest
python3 -m pytest tests/ -v
```

## نکات مهم پیاده‌سازی MVP (محدودیت‌های شناخته‌شده)

- **OCR مدارک**: اگر `tesseract` روی سرور نصب باشد (`pytesseract`)، استخراج واقعی متن/تاریخ انقضا انجام می‌شود. در غیر این صورت به‌صورت صادقانه `confidence=0` و `needs_manual_review` برمی‌گرداند — این fallback عمدی است، نه شبیه‌سازی موفق. برای فعال‌سازی کامل: `apt-get install tesseract-ocr tesseract-ocr-fas`.
- **تشخیص تجهیزات**: چون در این MVP هیچ مدل object-detection واقعی متصل نیست، از تطبیق شباهت تصویری (`perceptual hash`) نسبت به عکس‌های مرجع هر label در `equipment_references/` استفاده می‌شود (`scripts/generate_reference_assets.py` این مرجع‌ها را می‌سازد). در production باید `VisionProvider.analyze_equipment` با یک مدل vision واقعی (مثلاً یک multimodal LLM یا یک مدل object-detection آموزش‌دیده) جایگزین شود — رابط (`app/vision_provider.py`) از قبل برای این تعویض طراحی شده.
- **تشخیص عکس تکراری/reuse**: کاملاً واقعی و بدون نیاز به AI کار می‌کند (`imagehash.phash` + هامینگ دیستنس).
- برای اتصال به یک vision provider خارجی، `VASIQ_VISION_PROVIDER=external` را تنظیم کنید و کلاس `ExternalVisionProvider` را در `app/vision_provider.py` پیاده‌سازی کنید (در حال حاضر `NotImplementedError` می‌دهد).

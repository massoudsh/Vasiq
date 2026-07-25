# Vasiq — معماری فنی
## AI Provider Verification & Assignment Eligibility Engine

> نسخه ۰.۱ — سند طراحی اولیه (MVP → V1)

---

## ۱. مسئله و مرز مسئولیت

پلتفرم‌های عملیاتی (دلیوری، تاکسی اینترنتی، خدمات منزل، لجستیک، نیروی میدانی) امروز صلاحیت سرویس‌دهنده را عمدتاً یک‌بار، در زمان **onboarding**، می‌سنجند. Vasiq این سؤال را از «آیا این فرد اصلاً مجاز است؟» به «آیا این فرد **همین الان، برای همین مأموریت** مجاز است؟» تغییر می‌دهد.

Vasiq یک **decision layer** است، نه یک dispatch/assignment engine. ورودی‌اش provider + نوع مأموریت + مدارک/شواهد است؛ خروجی‌اش یک **eligibility decision** با دلیل، امتیاز ریسک و TTL است. تصمیم نهایی assignment را همچنان سیستم عملیاتی پلتفرم می‌گیرد؛ Vasiq فقط یک سیگنال معتبر و قابل‌استناد به آن می‌دهد.

### اصول طراحی
1. **Assignment-aware, not onboarding-only** — هر verification به یک `service_type` + `mission context` گره می‌خورد، نه فقط به پروفایل provider.
2. **Policy جدا از AI** — قوانین صلاحیت (چه مدرکی لازم است، چند روز اعتبار، چه تجهیزی) declarative و per-vertical است؛ مدل AI فقط «واقعیت را می‌خواند»، policy «تصمیم درست/غلط بودن» را می‌گیرد.
3. **Explainable** — هر decision باید فهرست دلایل (`reasons[]`) داشته باشد، نه فقط یک عدد.
4. **Cacheable با TTL** — بررسی مجدد کامل هر بار گران است؛ نتیجه با expiry مشخص cache می‌شود و فقط signal تغییر یا expiry باعث re-check می‌شود.
5. **Provider-agnostic AI** — لایه‌ی vision/OCR پشت یک interface است تا بتوان مدل/vendor را عوض کرد بدون تغییر در policy یا API عمومی.
6. **Multi-tenant از روز اول** — چون مدل کسب‌وکار B2B SaaS است، هر مشتری (پلتفرم) namespace و policy جدای خودش را دارد.

---

## ۲. مفاهیم دامنه (Domain Model)

| مفهوم | توضیح |
|---|---|
| **Tenant** | پلتفرم مشتری Vasiq (مثلاً یک اپ دلیوری). صاحب policy‌ها و providerها. |
| **ServiceType** | نوع مأموریت در آن tenant (مثلاً `food_delivery`, `ride_intercity`, `home_ac_repair`). هر ServiceType یک Policy فعال دارد. |
| **Provider** | سرویس‌دهنده (راننده/پیک/تکنسین). دارای مجموعه‌ای از Credential و Equipment claim. |
| **Credential** | یک مدرک (گواهینامه، کارت واکسیناسیون، بیمه، مدرک فنی) با تصویر/فایل پیوست، تاریخ صدور/انقضا، وضعیت استخراج‌شده توسط AI. |
| **EvidenceAsset** | هر تصویر/فایل خام (مدرک یا عکس تجهیزات) با metadata و perceptual hash برای تشخیص تکراری/reuse. |
| **Policy** | قانون صلاحیت یک ServiceType: مدارک الزامی، حداقل روز اعتبار باقی‌مانده، تجهیزات الزامی، سقف ریسک قابل‌قبول. نسخه‌دار (`policy_version`). |
| **AssignmentRequest** | درخواست بررسی صلاحیت برای یک provider مشخص در لحظه‌ی یک مأموریت مشخص. |
| **EligibilityCheck** | اجرای واقعی بررسی (run) روی یک AssignmentRequest؛ شامل نتیجه‌ی هر Verifier و امتیاز نهایی. |
| **EligibilityDecision** | خروجی نهایی: `eligible | not_eligible | conditional`، `risk_score`، `reasons[]`، `valid_until` (TTL). |
| **RiskEvent** | سیگنال‌های جانبی (شکایت مشتری، لغو مکرر، mismatch مدرک) که در risk score اثر می‌گذارد. |
| **AuditLog** | ثبت غیرقابل‌تغییر هر decision برای compliance و بازبینی. |

### رابطه‌ها (خلاصه)
```
Tenant 1───* ServiceType 1───1 Policy(active)
Tenant 1───* Provider 1───* Credential 1───1 EvidenceAsset
Provider 1───* RiskEvent
AssignmentRequest *───1 Provider
AssignmentRequest *───1 ServiceType
AssignmentRequest 1───1 EligibilityCheck 1───1 EligibilityDecision
EligibilityDecision 1───* AuditLog(append-only)
```

---

## ۳. Pipeline پردازش (per assignment request)

```
[1] Ingest
    ورودی: provider_id, service_type, tenant, (اختیاری) mission_context
    │
[2] Resolve Policy
    گرفتن نسخه‌ی فعال Policy برای این ServiceType
    │
[3] Load Provider State
    مدارک فعلی provider + آخرین EvidenceAsset هر کدام + RiskEvent های اخیر
    │
[4] Freshness Gate  ← بهینه‌سازی هزینه
    اگر برای همین provider+service_type یک Decision معتبر (valid_until > now)
    و بدون signal تغییر (مدرک جدید آپلود نشده، RiskEvent جدید نیامده) وجود دارد
    → همان را برگردان (cache hit، صفر هزینه‌ی AI)
    │  (در غیر این صورت ادامه)
[5] Run Verifiers (موازی، هرکدام مستقل)
    ├─ DocumentVerifier   → نوع مدرک را از تصویر می‌خواند + تاریخ انقضا را استخراج می‌کند
    ├─ EquipmentVerifier  → حضور تجهیز الزامی در عکس را تشخیص می‌دهد
    ├─ DuplicateDetector  → تصویر تکراری/reuse شده در بین providerهای دیگر یا زمان‌های قبلی
    └─ RiskScorer         → ترکیب RiskEventهای اخیر + نتایج بالا → یک عدد ریسک
    │
[6] Policy Evaluation (rule engine, بدون AI)
    نتایج مرحله‌ی ۵ را با Policy مقایسه می‌کند:
    مدرک الزامی موجود است؟ منقضی نشده (با در نظر گرفتن grace_days)؟
    تجهیز الزامی تشخیص داده شده؟ ریسک زیر سقف مجاز Policy است؟
    │
[7] Decision
    eligible / conditional (با شرط، مثلاً «فقط تا ۲ روز دیگر معتبر») / not_eligible
    + reasons[] + risk_score + valid_until (TTL)
    │
[8] Persist + Audit
    EligibilityCheck + EligibilityDecision + AuditLog ذخیره می‌شود
    │
[9] Respond
```

**بودجه‌ی زمانی:** چون این تصمیم در لحظه‌ی assignment (real-time) استفاده می‌شود، مسیر cache-hit باید زیر ۱۰۰ms باشد؛ مسیر full-run (فراخوانی AI) در MVP هدف‌گذاری زیر ۳-۵ ثانیه دارد (قابل بهبود با پردازش async + webhook برای مواردی که provider هنوز مدرک تازه آپلود نکرده).

---

## ۴. Policy Engine

Policy کاملاً **declarative** و جدا از کد است (فایل JSON per service type، نسخه‌دار). نمونه:

```json
{
  "service_type": "food_delivery_bike",
  "policy_version": "2026-07-01",
  "required_credentials": [
    { "type": "motorcycle_license", "min_days_valid": 30 },
    { "type": "vehicle_insurance",  "min_days_valid": 15, "grace_days": 3 }
  ],
  "required_equipment": [
    { "type": "delivery_box", "min_confidence": 0.75 },
    { "type": "helmet",       "min_confidence": 0.8 }
  ],
  "risk": {
    "max_score": 65,
    "conditional_band": [50, 65]
  },
  "duplicate_photo_policy": "reject"
}
```

منطق ارزیابی (بدون هیچ فراخوانی AI) در `policy_engine.py` خالص و تست‌پذیر است: ورودی = خروجی verifierها + policy، خروجی = decision + reasons. این جداسازی یعنی تغییر قوانین کسب‌وکار نیاز به تغییر مدل یا کد AI ندارد.

---

## ۵. لایه‌ی AI / Vision (Provider-agnostic)

```
VisionProvider (interface)
   analyze_document(image) -> {doc_type, fields{expiry_date,...}, confidence}
   analyze_equipment(image, target_labels) -> {label: confidence, ...}

پیاده‌سازی‌ها:
   - HeuristicVisionProvider  (MVP آفلاین: OCR + رنگ/لبه/EXIF — بدون کلید API)
   - ExternalVisionProvider   (production: مدل multimodal خارجی، پشت همان interface)
```

این جداسازی یعنی می‌توان vendor مدل vision را (OpenAI/Gemini/داخلی) بدون تغییر در `eligibility.py` یا `policy_engine.py` عوض کرد — فقط `VASIQ_VISION_PROVIDER` در تنظیمات عوض می‌شود.

**DuplicateDetector** از perceptual hashing (`imagehash`) استفاده می‌کند تا عکس‌های reuse-شده (همان عکس تجهیزات برای مأموریت‌های مختلف، یا مدرک کپی‌شده بین چند provider) را بدون نیاز به AI گران تشخیص دهد — این یک سیگنال ارزان و مؤثر ضدتقلب است.

---

## ۶. Risk Scoring

Risk score ترکیبی است از:
- سیگنال‌های خودِ verification (مدرک نزدیک انقضا، mismatch بین OCR و پروفایل، عکس مشکوک/تکراری)
- `RiskEvent` های تاریخی provider (شکایت، لغو مکرر، گزارش ایمنی) — با weighted decay بر اساس زمان
- فرکانس assignment اخیر در بازه‌ی کوتاه (سیگنال fraud/فرسودگی)

خروجی یک عدد ۰-۱۰۰ است که Policy سقف مجاز و «باند شرطی» را روی آن تعریف می‌کند — منطق وزن‌دهی در `risk_scorer.py` است و مستقل از policy تست می‌شود.

---

## ۷. API Contract (خلاصه — نسخه‌ی کامل در OpenAPI خودکار FastAPI: `/docs`)

| Method | Path | توضیح |
|---|---|---|
| `POST` | `/v1/providers` | ثبت provider |
| `POST` | `/v1/providers/{id}/credentials` | آپلود مدرک (multipart) |
| `POST` | `/v1/providers/{id}/equipment-photos` | آپلود عکس تجهیزات |
| `POST` | `/v1/eligibility/check` | **اصلی‌ترین endpoint** — بررسی صلاحیت per assignment |
| `GET`  | `/v1/eligibility/{decision_id}` | واکشی یک decision قبلی |
| `GET`  | `/v1/providers/{id}/history` | تاریخچه‌ی decisionها برای audit |
| `PUT`  | `/v1/policies/{service_type}` | ثبت/به‌روزرسانی policy (نسخه‌دار) |

`POST /v1/eligibility/check` — نمونه request/response:
```json
// Request
{ "tenant_id": "tnt_123", "provider_id": "prv_88", "service_type": "food_delivery_bike" }

// Response
{
  "decision": "conditional",
  "risk_score": 42,
  "valid_until": "2026-07-26T18:00:00Z",
  "reasons": [
    "credential.vehicle_insurance: valid, expires in 4 days (within grace period)",
    "equipment.delivery_box: detected (confidence 0.91)",
    "equipment.helmet: NOT detected (confidence 0.31 < 0.8)"
  ]
}
```

---

## ۸. مدل داده (جدول‌های اصلی — پیاده‌سازی در `backend/app/models.py`)

`tenants, service_types, policies, providers, credentials, evidence_assets, risk_events, assignment_requests, eligibility_checks, eligibility_decisions, audit_logs`

جزئیات ستون‌ها در ORM (SQLAlchemy) منبع حقیقت است؛ این سند فقط رابطه‌ی مفهومی را نشان می‌دهد (بخش ۲).

---

## ۹. Non-functional

- **Compliance/PII**: تصاویر مدارک هویتی حساس‌اند؛ در MVP روی دیسک محلی با path غیرقابل‌حدس ذخیره می‌شوند؛ در production باید encrypted object storage + access log جدا شود.
- **Auditability**: هر Decision یک رکورد AuditLog تغییرناپذیر دارد (append-only) — برای اثبات compliance به قانون‌گذار/بیمه.
- **Multi-tenant isolation**: هر query با `tenant_id` filter می‌شود؛ در V1 باید سطح DB (row-level security) هم اضافه شود.
- **Idempotency**: `POST /v1/eligibility/check` باید idempotent روی (provider_id, service_type, freshness window) باشد تا فراخوانی مکرر هزینه‌ی AI تکراری نسازد.

---

## ۱۰. نقشه‌ی راه

| فاز | محدوده |
|---|---|
| **MVP (این تحویل)** | API کامل + Policy Engine + Heuristic Vision (OCR واقعی، بدون نیاز به کلید خارجی) + Duplicate Detection + Risk Scorer + SQLite |
| **V1** | اتصال به یک Vision LLM واقعی (پشت همان interface)، Postgres، multi-tenant واقعی، webhook برای async verification، rate limiting per tenant |
| **V2** | یادگیری از بازخورد عملیاتی (outcome feedback loop: آیا assignmentهایی که eligible تشخیص داده شدیم واقعاً مشکل نداشتند؟)، continuous re-scoring بدون trigger دستی، marketplace از verticalهای مختلف (دلیوری → تاکسی → خدمات منزل → لجستیک) |

نقطه‌ی ورود پیشنهادی بازار: **AI Box Verification برای دلیوری** (تشخیص جعبه‌ی دلیوری استاندارد در عکس provider) — pain نقطه‌ای و ROI قابل‌اندازه‌گیری (کاهش QC دستی، کاهش شکایت کیفیت بسته‌بندی)، سپس گسترش به سایر ServiceTypeها با همین موتور.

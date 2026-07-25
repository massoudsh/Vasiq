"""تنظیمات سراسری Vasiq.

مقادیر از متغیرهای محیطی خوانده می‌شوند تا استقرار در محیط‌های مختلف
(dev/staging/prod) بدون تغییر کد ممکن باشد.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "Vasiq"
    database_url: str = f"sqlite:///{BASE_DIR / 'vasiq.db'}"
    storage_dir: Path = BASE_DIR / "storage"
    policies_dir: Path = BASE_DIR / "policies"

    # لایه‌ی AI: در MVP از heuristic (OCR واقعی + تحلیل تصویر بدون کلید API)
    # استفاده می‌شود. برای اتصال به یک مدل vision خارجی در production،
    # این مقدار را به external تغییر دهید و کلید را در VASIQ_VISION_API_KEY بگذارید.
    vision_provider: str = "heuristic"
    vision_api_key: str | None = None

    # اگر برای یک provider+service_type تصمیم معتبر (valid_until > now) وجود
    # داشته باشد و سیگنال تغییری نیامده باشد، بدون اجرای دوباره‌ی verifierها
    # همان تصمیم برگردانده می‌شود (cache hit).
    default_decision_ttl_hours: int = 24

    model_config = SettingsConfigDict(env_prefix="VASIQ_")


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)

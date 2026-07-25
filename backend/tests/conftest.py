import os
import tempfile
from pathlib import Path

import pytest

# باید قبل از هر import از app تنظیم شود چون Settings در import-time خوانده می‌شود.
_tmp_root = Path(tempfile.mkdtemp())
os.environ["VASIQ_DATABASE_URL"] = f"sqlite:///{_tmp_root / 'vasiq_test.db'}"
os.environ["VASIQ_STORAGE_DIR"] = str(_tmp_root / "storage")

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)

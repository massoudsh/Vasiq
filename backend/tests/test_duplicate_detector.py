from PIL import Image, ImageDraw

from app.scanners.duplicate_detector import compute_phash, find_duplicates


def _save_png(tmp_path, name, color):
    path = tmp_path / name
    Image.new("RGB", (128, 128), color).save(path)
    return path


def _save_patterned_png(tmp_path, name, bg, shape):
    # phash بر اساس بافت/الگوی تصویر کار می‌کند نه رنگ خام؛ دو تصویر تک‌رنگ و
    # بدون بافت همیشه hash یکسان می‌گیرند (رفتار صحیح الگوریتم). برای تست تمایز
    # باید الگوهای بصری متفاوت بسازیم.
    path = tmp_path / name
    img = Image.new("RGB", (128, 128), bg)
    draw = ImageDraw.Draw(img)
    if shape == "rect":
        draw.rectangle((10, 10, 60, 118), fill=(255, 255, 255))
    else:
        draw.ellipse((70, 10, 118, 118), fill=(0, 0, 0))
    img.save(path)
    return path


def test_identical_images_have_zero_distance(tmp_path):
    p1 = _save_png(tmp_path, "a.png", (10, 20, 30))
    p2 = _save_png(tmp_path, "b.png", (10, 20, 30))
    h1, h2 = compute_phash(p1), compute_phash(p2)
    assert (h1 - h2) == 0


def test_different_images_have_larger_distance(tmp_path):
    p1 = _save_patterned_png(tmp_path, "a.png", (200, 200, 200), "rect")
    p2 = _save_patterned_png(tmp_path, "b.png", (30, 30, 30), "ellipse")
    h1, h2 = compute_phash(p1), compute_phash(p2)
    assert (h1 - h2) > 0


def test_find_duplicates_excludes_same_provider(client, tmp_path):
    from app.database import SessionLocal
    from app.models import EvidenceAsset

    db = SessionLocal()
    try:
        p1 = _save_png(tmp_path, "a.png", (50, 60, 70))
        h = str(compute_phash(p1))

        db.add(EvidenceAsset(provider_id="prv_self", kind="equipment_photo", file_path=str(p1), phash=h))
        db.commit()

        matches = find_duplicates(db, h, exclude_provider_id="prv_self")
        assert matches == []

        db.add(EvidenceAsset(provider_id="prv_other", kind="equipment_photo", file_path=str(p1), phash=h))
        db.commit()

        matches = find_duplicates(db, h, exclude_provider_id="prv_self")
        assert len(matches) == 1
        assert matches[0].provider_id == "prv_other"
    finally:
        db.close()

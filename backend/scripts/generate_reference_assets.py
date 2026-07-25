"""تولید تصاویر مرجع تجهیزات (equipment_references) — swatchهای ساده‌ی synthetic.

این تصاویر جایگزین یک مدل object-detection واقعی برای EquipmentVerifier در MVP
هستند (بخش ۵ سند معماری): عکس آپلودی provider با این مرجع‌ها با perceptual hash
مقایسه می‌شود. در production باید با یک مدل vision واقعی جایگزین شوند.
"""
from pathlib import Path

from PIL import Image, ImageDraw

REFS_DIR = Path(__file__).resolve().parent.parent / "equipment_references"
REFS_DIR.mkdir(parents=True, exist_ok=True)

SWATCHES = {
    "delivery_box": {"bg": (230, 126, 34), "shape": "rect"},
    "helmet": {"bg": (192, 57, 43), "shape": "ellipse"},
    "toolkit": {"bg": (52, 73, 94), "shape": "rect"},
    "safety_gear": {"bg": (241, 196, 15), "shape": "ellipse"},
    "cargo_seal_kit": {"bg": (39, 174, 96), "shape": "rect"},
}


def make_swatch(bg, shape, size=256) -> Image.Image:
    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)
    inset = size // 6
    box = (inset, inset, size - inset, size - inset)
    fill = tuple(min(255, c + 40) for c in bg)
    if shape == "rect":
        draw.rectangle(box, fill=fill, outline=(0, 0, 0), width=4)
    else:
        draw.ellipse(box, fill=fill, outline=(0, 0, 0), width=4)
    return img


def main() -> None:
    for label, cfg in SWATCHES.items():
        img = make_swatch(cfg["bg"], cfg["shape"])
        out = REFS_DIR / f"{label}.png"
        img.save(out)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()

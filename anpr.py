"""
anpr.py – Automatic Number Plate Recognition
Uses EasyOCR to extract licence-plate text from a vehicle bounding box.
"""

import re
import numpy as np

_ocr_reader = None          # module-level singleton


# ── public API ────────────────────────────────────────────────────────────────

def initialize_anpr() -> bool:
    """Load EasyOCR into memory (call once at start-up).  Returns True on success."""
    global _ocr_reader
    if _ocr_reader is not None:
        return True

    print("[ANPR] Loading EasyOCR model …")
    try:
        import easyocr
        _ocr_reader = easyocr.Reader(["en"], gpu=False)
        print("[ANPR] EasyOCR ready.")
        return True
    except Exception as exc:
        print(f"[ANPR] Failed to load EasyOCR: {exc}")
        return False


def get_plate_text(frame: np.ndarray, box: tuple) -> str:
    """
    Return the best licence-plate string found inside *box* (x1,y1,x2,y2).
    Returns 'N/A' when nothing valid is detected.
    """
    if _ocr_reader is None:
        print("[ANPR] Not initialised – call initialize_anpr() first.")
        return "N/A"

    x1, y1, x2, y2 = map(int, box)
    bh, bw = y2 - y1, x2 - x1

    # Smart crop: bottom 40 % vertical, centre 80 % horizontal
    cy1 = y2 - int(bh * 0.40)
    cx1 = x1 + int(bw * 0.10)
    cx2 = x2 - int(bw * 0.10)

    crop = frame[max(cy1, 0):y2, max(cx1, 0):cx2]
    if crop.shape[0] < 20 or crop.shape[1] < 40:
        return "N/A"

    try:
        for raw in _ocr_reader.readtext(crop, detail=0):
            text = re.sub(r"[^A-Z0-9]", "", raw.upper())
            if 4 <= len(text) <= 10:
                print(f"[ANPR] Plate detected: {text}")
                return text
    except Exception as exc:
        print(f"[ANPR] OCR error: {exc}")

    return "N/A"


# Backwards-compatible alias
def get_plate_from_frame(frame: np.ndarray, box) -> str:
    return get_plate_text(frame, box)
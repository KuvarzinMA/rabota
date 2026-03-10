import fitz
import hashlib
import numpy as np
import cv2
from PIL import Image
from pyzbar.pyzbar import decode
from config import QR_SECRET


def verify_md5(full_text, secret=QR_SECRET):
    parts = full_text.rsplit("-", 1)
    if len(parts) != 2: return False
    # Важно: кодируем в utf-8 перед хешированием
    expected = hashlib.md5((parts[0] + secret).encode("utf-8")).hexdigest()
    return expected == parts[1]


def scan_pdf_qr(pdf_bytes):
    # Открываем из памяти
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    detector = cv2.QRCodeDetector()
    all_results = []

    # Твои рабочие коэффициенты
    ROI_RATIO = 0.4
    FAST_DPI = 220
    FALLBACK_ZOOM = 3.5

    for idx, page in enumerate(doc, start=1):
        rect = page.rect
        # Четкая область ROI: верхний левый угол
        clip = fitz.Rect(
            rect.width * (1 - ROI_RATIO),  # Начало по X (справа)
            rect.y0,  # Начало по Y (верх)
            rect.x1,  # Конец по X (край листа)
            rect.y0 + rect.height * ROI_RATIO  # Конец по Y
        )

        # --- ШАГ 1: FAST PASS (PyZbar) ---
        pix = page.get_pixmap(dpi=FAST_DPI, clip=clip)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        decoded = decode(img)

        found_on_page = False
        if decoded:
            for obj in decoded:
                text = obj.data.decode("utf-8")
                all_results.append((idx, text, verify_md5(text)))
                found_on_page = True

        if found_on_page:
            continue  # Нашли — идем к следующей странице

        # --- ШАГ 2: FALLBACK (OpenCV) ---
        print(f"Fallback на странице {idx}")
        mat = fitz.Matrix(FALLBACK_ZOOM, FALLBACK_ZOOM)
        pix = page.get_pixmap(matrix=mat, clip=clip)

        # Конвертация в BGR для OpenCV
        img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

        ok, infos, _, _ = detector.detectAndDecodeMulti(img_np)
        if ok:
            for data in infos:
                if data:
                    all_results.append((idx, data, verify_md5(data)))

    return all_results
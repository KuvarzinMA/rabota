import fitz
import hashlib
import numpy as np
import cv2
from PIL import Image
from pyzbar.pyzbar import decode
import time

start_time = time.time()

PDF_PATH = "qr-code.pdf"
secret = "secret"

# ROI — левый верхний угол
ROI_RATIO = 0.4

# zoom уровни
FAST_DPI = 220
FALLBACK_ZOOM = 3.5


# ---------------- MD5 ----------------

def generate_md5_checksum(txt: str, secret: str) -> str:
    return hashlib.md5((txt + secret).encode("utf-8")).hexdigest()


def verify_md5_checksum(full_text: str, secret: str, sep="-") -> bool:
    parts = full_text.rsplit(sep, 1)
    if len(parts) != 2:
        return False
    txt, given = parts
    return generate_md5_checksum(txt, secret) == given


# ---------------- UTILS ----------------

def pixmap_to_bgr(pix):
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


# ---------------- FAST PASS (pyzbar) ----------------

def fast_pyzbar_scan(page, page_index):
    rect = page.rect

    clip = fitz.Rect(
        rect.x0,
        rect.y0,
        rect.x0 + rect.width * ROI_RATIO,
        rect.y0 + rect.height * ROI_RATIO,
    )

    pix = page.get_pixmap(dpi=FAST_DPI, clip=clip)

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    decoded = decode(img)

    results = []

    for obj in decoded:
        text = obj.data.decode("utf-8")

        results.append((page_index, text, verify_md5_checksum(text, secret)))

    return results


# ---------------- FALLBACK PASS (OpenCV) ----------------

def fallback_opencv_scan(page, page_index, detector):
    rect = page.rect

    clip = fitz.Rect(
        rect.x0,
        rect.y0,
        rect.x0 + rect.width * ROI_RATIO,
        rect.y0 + rect.height * ROI_RATIO,
    )

    mat = fitz.Matrix(FALLBACK_ZOOM, FALLBACK_ZOOM)
    pix = page.get_pixmap(matrix=mat, clip=clip)

    img = pixmap_to_bgr(pix)

    ok, infos, points, _ = detector.detectAndDecodeMulti(img)

    results = []

    if ok:
        for data in infos:
            if data:
                results.append(
                    (page_index, data, verify_md5_checksum(data, secret))
                )

    return results


# ---------------- MAIN ----------------

def scan_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    detector = cv2.QRCodeDetector()

    all_results = []

    for page_index, page in enumerate(doc, start=1):

        # FAST PASS
        fast_results = fast_pyzbar_scan(page, page_index)

        if fast_results:
            all_results.extend(fast_results)
            continue  # QR найден — fallback не нужен

        # FALLBACK
        fallback_results = fallback_opencv_scan(page, page_index, detector)

        all_results.extend(fallback_results)

    return all_results


# ---------------- RUN ----------------

if __name__ == "__main__":
    results = scan_pdf(PDF_PATH)

    for page, text, valid in results:
        print(f"Страница {page}: {text}")
        print("Контрольная сумма верна" if valid else "Контрольная сумма НЕ совпадает")

end_time = time.time()  # конец таймера
elapsed = end_time - start_time
print(f"Время выполнения: {elapsed:.2f} секунд")
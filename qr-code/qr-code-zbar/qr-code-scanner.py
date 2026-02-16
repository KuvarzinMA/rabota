import fitz
import hashlib
from PIL import Image
from pyzbar.pyzbar import decode
import time

start_time = time.time()

def generate_md5_checksum(txt: str, secret: str) -> str:
    combined = txt + secret
    return hashlib.md5(combined.encode("utf-8")).hexdigest()


def verify_md5_checksum(full_text: str, secret: str, sep: str = "-") -> bool:
    parts = full_text.rsplit(sep, 1)
    if len(parts) != 2:
        return False

    txt, given_checksum = parts
    calc_checksum = generate_md5_checksum(txt, secret)
    return calc_checksum == given_checksum


def scan_qr(pdf_path, secret, roi_ratio=0.35, dpi=300):
    results = []
    doc = fitz.open(pdf_path)

    for i, page in enumerate(doc):
        rect = page.rect

        # Только левый верхний угол
        clip = fitz.Rect(
            rect.x0,
            rect.y0,
            rect.x0 + rect.width * roi_ratio,
            rect.y0 + rect.height * roi_ratio
        )

        pix = page.get_pixmap(dpi=dpi, clip=clip)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        decoded = decode(img)

        for obj in decoded:
            text = obj.data.decode("utf-8")

            # проверяем checksum
            is_valid = verify_md5_checksum(text, secret)

            results.append({
                "page": i + 1,
                "data": text,
                "valid": is_valid,
                "type": obj.type
            })

    return results


if __name__ == "__main__":
    secret = "secret"

    res = scan_qr("qr_pymupdf.pdf", secret)

    for r in res:
        if r["valid"]:
            print(f"[OK][page {r['page']}] {r['data']}")
        else:
            print(f"[BAD][page {r['page']}] {r['data']}")


end_time = time.time()  # конец таймера
elapsed = end_time - start_time
print(f"Время выполнения: {elapsed:.2f} секунд")
import fitz
import hashlib
import numpy as np
import cv2
import boto3
import psycopg2
import select
from PIL import Image
from pyzbar.pyzbar import decode

# --- CONFIG ---
DB_CONFIG = {
    "host": "10.2.1.50",
    "database": "rpismo",
    "user": "rpismo",
    "password": "22rpismo11"
}

S3_CONFIG = {
    "endpoint_url": "http://10.2.1.50:9000",
    "aws_access_key_id": "minioadmin",
    "aws_secret_access_key": "minioadmin",
}

# Укажи название своего бакета в MinIO
BUCKET_NAME = "test-bucket"
SECRET = "secret"

# Параметры сканирования из твоего исходника
ROI_RATIO = 0.4
FAST_DPI = 220
FALLBACK_ZOOM = 3.5

s3_client = boto3.client('s3', **S3_CONFIG)


def verify_md5_checksum(full_text: str, secret: str) -> bool:
    parts = full_text.rsplit("-", 1)
    if len(parts) != 2: return False
    txt, given = parts
    return hashlib.md5((txt + secret).encode("utf-8")).hexdigest() == given


def pixmap_to_bgr(pix):
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR) if pix.n == 4 else img


def process_file(pdf_bytes):
    """Логика распознавания"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    detector = cv2.QRCodeDetector()
    results = []

    for idx, page in enumerate(doc, start=1):
        rect = page.rect
        clip = fitz.Rect(rect.x0, rect.y0, rect.x0 + rect.width * ROI_RATIO, rect.y0 + rect.height * ROI_RATIO)

        # Fast Pass
        pix = page.get_pixmap(dpi=FAST_DPI, clip=clip)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        decoded = decode(img)

        if decoded:
            for obj in decoded:
                text = obj.data.decode("utf-8")
                results.append((idx, text, verify_md5_checksum(text, SECRET)))
            continue  # Если нашли, идем к следующей странице

        # Fallback
        mat = fitz.Matrix(FALLBACK_ZOOM, FALLBACK_ZOOM)
        pix = page.get_pixmap(matrix=mat, clip=clip)
        img = pixmap_to_bgr(pix)
        ok, infos, _, _ = detector.detectAndDecodeMulti(img)
        if ok:
            for data in infos:
                if data:
                    results.append((idx, data, verify_md5_checksum(data, SECRET)))
    return results


def handle_notification(record_id):
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            # Тянем stor_url по id
            cur.execute("SELECT stor_url FROM proc_files WHERE id = %s", (record_id,))
            row = cur.fetchone()
            if not row:
                print(f"ID {record_id} не найден.")
                return

            file_key = row[0]
            print(f"Обработка файла: {file_key}")

            # Загрузка из MinIO
            response = s3_client.get_object(Bucket=BUCKET_NAME, Key=file_key)
            pdf_data = response['Body'].read()

            # Распознавание
            found_qrs = process_file(pdf_data)

            if found_qrs:
                for page, text, is_valid in found_qrs:
                    print(f"Стр {page}: {text} | Валиден: {is_valid}")
                # Обновляем статус на 'success'
                cur.execute("UPDATE proc_files SET processed = 0 WHERE id = %s", (record_id,))
            else:
                print(f"QR не найден в файле {record_id}")
                cur.execute("UPDATE proc_files SET processed = 2 WHERE id = %s", (record_id,))

            conn.commit()
    except Exception as e:
        print(f"Ошибка воркера: {e}")
    finally:
        conn.close()


def run_worker():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("LISTEN new_scan;")
    print("Воркер запущен и ждет NOTIFY new_scan...")

    while True:
        if select.select([conn], [], [], 5) != ([], [], []):
            conn.poll()
            while conn.notifies:
                msg = conn.notifies.pop(0)
                print(f"Событие для ID: {msg.payload}")
                handle_notification(msg.payload)


if __name__ == "__main__":
    run_worker()

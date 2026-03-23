import time
import re
from config import S3_BUCKET


class DocumentProcessor:
    """Отвечает за логику распознавания и классификации документа."""
    RE_WSNA = re.compile(r"wsna-(\d+)")
    RE_ANSW = re.compile(r"answ-(\d+)")

    def __init__(self, ocr_engine, qr_scanner):
        self.ocr = ocr_engine
        self.scan_qr = qr_scanner

    def get_document_info(self, pdf_bytes):
        """Разбирает QR и извлекает телефон, если нужно."""
        qr_results = self.scan_qr(pdf_bytes)
        valid_qr = next((r for r in qr_results if r[2]), None)

        if not valid_qr:
            return {"status": "error", "reason": "QR_NOT_FOUND", "raw": qr_results[0][1] if qr_results else None}

        qr_text = valid_qr[1]

        # Определяем тип документа
        if "rpismo-wsna-" in qr_text:
            match = self.RE_WSNA.search(qr_text)
            return {"status": "success", "type": "answer", "id": int(match.group(1)) if match else None}

        if "rpismo-answ-" in qr_text:
            match = self.RE_ANSW.search(qr_text)
            phone = self.ocr.extract_phone(pdf_bytes)
            return {
                "status": "success",
                "type": "init",
                "id": int(match.group(1)) if match else None,
                "phone": phone,
                "qr_text": qr_text
            }

        return {"status": "error", "reason": "UNKNOWN_QR_TYPE", "qr_text": qr_text}


class StorageService:
    """Отвечает только за доставку байтов из S3."""

    def __init__(self, s3_client):
        self.s3 = s3_client

    def download(self, key, retries=3):
        for attempt in range(retries):
            try:
                obj = self.s3.get_object(Bucket=S3_BUCKET, Key=key)
                return obj["Body"].read()
            except Exception:
                if attempt == retries - 1: raise
                time.sleep(2)
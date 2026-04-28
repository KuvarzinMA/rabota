import logging
import re
import time


logger = logging.getLogger("worker.services")


class DocumentProcessor:
    """Отвечает за распознавание и классификацию документа по QR-коду."""

    RE_WSNA = re.compile(r"wsna-(\d+)")
    RE_ANSW = re.compile(r"answ-(\d+)")

    def __init__(self, ocr_engine, qr_scanner):
        self.ocr = ocr_engine
        self.scan_qr = qr_scanner

    def get_document_info(self, pdf_bytes: bytes) -> dict:
        """
        Анализирует PDF и возвращает словарь с результатом.

        Возможные статусы:
          {"status": "error",   "reason": str, "qr_text": str | None}
          {"status": "success", "type": "answer", "id": int}
          {"status": "success", "type": "init",   "id": int, "phone": str | None, "qr_text": str}
        """
        qr_results = self.scan_qr(pdf_bytes)
        valid_qr = next((r for r in qr_results if r[2]), None)

        if not valid_qr:
            raw = qr_results[0][1] if qr_results else None
            return {"status": "error", "reason": "QR_NOT_FOUND", "qr_text": raw}

        qr_text = valid_qr[1]

        if "rpismo-wsna-" in qr_text:
            match = self.RE_WSNA.search(qr_text)
            if not match:
                return {"status": "error", "reason": "QR_PARSE_FAILED", "qr_text": qr_text}
            return {"status": "success", "type": "answer", "id": int(match.group(1))}

        if "rpismo-answ-" in qr_text:
            match = self.RE_ANSW.search(qr_text)
            if not match:
                return {"status": "error", "reason": "QR_PARSE_FAILED", "qr_text": qr_text}
            phone = self.ocr.extract_phone(pdf_bytes)
            return {
                "status": "success",
                "type": "init",
                "id": int(match.group(1)),
                "phone": phone,
                "qr_text": qr_text,
            }

        return {"status": "error", "reason": "UNKNOWN_QR_TYPE", "qr_text": qr_text}


class StorageService:
    """Отвечает только за доставку байтов из S3/MinIO."""

    def __init__(self, s3_client):
        self.s3 = s3_client

    def download(self, bucket_name: str, key: str, retries: int = 3) -> bytes:
        """Скачивает файл из S3 с экспоненциальными повторами."""
        for attempt in range(retries):
            try:
                obj = self.s3.get_object(Bucket=bucket_name, Key=key)
                return obj["Body"].read()
            except Exception as e:
                logger.warning(f"S3 попытка {attempt + 1}/{retries} для '{key}': {e}")
                if attempt == retries - 1:
                    raise RuntimeError(
                        f"Не удалось скачать '{key}' после {retries} попыток"
                    ) from e
                time.sleep(2 ** attempt)  # 1с → 2с → 4с
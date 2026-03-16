import logging
import re
import select
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
import boto3

from config import *
import queries
from qr_service import scan_pdf_qr
from phone_ocr import PhoneOCR

# 1. НАСТРОЙКА ЛОГИРОВАНИЯ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("worker.log", encoding="utf-8"),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)

# 2. РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ
RE_WSNA = re.compile(r"wsna-(\d+)")
RE_ANSW = re.compile(r"answ-(\d+)")

# 3. ПУЛ СОЕДИНЕНИЙ С БАЗОЙ
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
    logger.info("PostgreSQL pool успешно инициализирован")
except Exception as e:
    logger.critical(f"Ошибка пула БД: {e}")
    exit(1)


@contextmanager
def get_db():
    """Безопасное получение соединения из пула."""
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        db_pool.putconn(conn)


# 4. ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ
s3 = boto3.client("s3", **S3_CONFIG)
ocr = PhoneOCR()
executor = ThreadPoolExecutor(max_workers=4)


# 5. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
def download_file_from_s3(key, retries=3, delay=3):
    """Загрузка файла с механизмом повторов."""
    for attempt in range(retries):
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            return obj["Body"].read()
        except s3.exceptions.NoSuchKey:
            if attempt == retries - 1:
                raise
            logger.warning(f"Файл {key} не найден, попытка {attempt + 1}")
            time.sleep(delay)
    return None


def process_qr(qr_text, record_id, stor_url, pdf_bytes, cur):
    """Разбор QR и выполнение бизнес-логики."""
    # Случай: Ответ на письмо
    if "rpismo-wsna-" in qr_text:
        match = RE_WSNA.search(qr_text)
        if not match:
            raise ValueError("Неверный формат wsna")

        letter_id = int(match.group(1))
        queries.update_as_answer(cur, record_id, letter_id, stor_url)
        logger.info(f"ID {record_id}: привязан как ОТВЕТ к {letter_id}")

    # Случай: Новое (инициативное) письмо
    elif "rpismo-answ-" in qr_text:
        match = RE_ANSW.search(qr_text)
        if not match:
            raise ValueError("Неверный формат answ")

        blank_id = int(match.group(1))
        phone = ocr.extract_phone(pdf_bytes)

        if not phone:
            queries.mark_as_error(cur, record_id, stor_url, "OCR failed", qr_text=qr_text)
            return

        success, res = queries.create_init_letter(cur, record_id, blank_id, stor_url, phone)
        if not success:
            queries.mark_as_error(cur, record_id, stor_url, res, qr_text=qr_text)
        else:
            logger.info(f"ID {record_id}: создано письмо {res} для {phone}")

    else:
        queries.mark_as_error(cur, record_id, stor_url, f"Неизвестный QR: {qr_text}", qr_text=qr_text)


# 6. ОСНОВНЫЕ ОБРАБОТЧИКИ
def handle_notification(payload):
    """Обработка одной задачи из очереди."""
    start_time = time.perf_counter()
    record_id, stor_url = int(payload), "Unknown"

    try:
        with get_db() as (conn, cur):
            stor_url = queries.get_file_info(cur, record_id)
            if not stor_url:
                logger.warning(f"ID {record_id} не найден")
                return

            logger.info(f">>> Обработка ID {record_id} ({stor_url})")

            pdf_bytes = download_file_from_s3(stor_url)
            qr_results = scan_pdf_qr(pdf_bytes)

            # Ищем первый валидный QR
            valid_qr = next((r for r in qr_results if r[2]), None)

            if not valid_qr:
                msg = qr_results[0][1] if qr_results else "QR не найден"
                queries.mark_as_error(cur, record_id, stor_url, f"Невалидный QR: {msg}")
                return

            process_qr(valid_qr[1], record_id, stor_url, pdf_bytes, cur)

        elapsed = time.perf_counter() - start_time
        logger.info(f"<<< ID {record_id} завершен за {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Ошибка ID {record_id}: {e}")
        try:
            with get_db() as (_, cur):
                queries.mark_as_error(cur, record_id, stor_url, f"System error: {e}")
        except Exception:
            logger.critical("Не удалось записать ошибку в базу!")


def listen_notifications():
    """Цикл ожидания уведомлений от Postgres."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("LISTEN new_scan;")

    logger.info("Воркер запущен и ждет событий...")

    while True:
        # Ждем события с таймаутом, чтобы не блокировать процесс навсегда
        if select.select([conn], [], [], 5) == ([], [], []):
            continue

        conn.poll()
        while conn.notifies:
            notify = conn.notifies.pop(0)
            executor.submit(handle_notification, notify.payload)


# 7. ЗАПУСК
if __name__ == "__main__":
    try:
        # Проверка зависших задач при старте
        with get_db() as (_, cur):
            pending = queries.get_pending_tasks(cur)
            if pending:
                logger.info(f"Найдено {len(pending)} задач в очереди")
                for pid in pending:
                    executor.submit(handle_notification, pid)

        listen_notifications()

    except KeyboardInterrupt:
        logger.info("Воркер остановлен пользователем")
    finally:
        executor.shutdown(wait=True)
        db_pool.closeall()
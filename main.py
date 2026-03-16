import logging
import re
import select
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import wraps

import psycopg2
from psycopg2 import pool
import boto3

from config import *
import queries
from qr_service import scan_pdf_qr
from phone_ocr import PhoneOCR

# =========================================================
# 1. ЛОГИРОВАНИЕ
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("worker.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =========================================================
# 2. РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ И ГЛОБАЛЫ
# =========================================================
RE_WSNA = re.compile(r"wsna-(\d+)")
RE_ANSW = re.compile(r"answ-(\d+)")

# Сервисы
s3 = boto3.client("s3", **S3_CONFIG)
ocr = PhoneOCR()
executor = ThreadPoolExecutor(max_workers=4)

# =========================================================
# 3. РАБОТА С БАЗОЙ ДАННЫХ И РЕКОННЕКТ
# =========================================================
try:
    # Используем ThreadedConnectionPool для безопасной работы в потоках
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, **DB_CONFIG)
    logger.info("Пул соединений PostgreSQL инициализирован")
except Exception as e:
    logger.critical(f"Критическая ошибка пула БД: {e}")
    exit(1)


def retry_db(retries=3, delay=2):
    """Декоратор для повторных попыток при сбое связи с БД."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                    if attempt == retries - 1: raise
                    logger.warning(f"Сбой БД (попытка {attempt + 1}): {e}. Ждем {delay}с...")
                    time.sleep(delay)
            return None

        return wrapper

    return decorator


@contextmanager
def get_db():
    """Менеджер транзакций с проверкой 'живучести' соединения."""
    conn = db_pool.getconn()
    try:
        # Проверка: если соединение упало, пробуем восстановить
        if conn.closed != 0:
            conn = db_pool.getconn()

        cur = conn.cursor()
        yield conn, cur
        conn.commit()  # Фиксация изменений
    except Exception as e:
        conn.rollback()  # Откат при любой ошибке
        raise e
    finally:
        db_pool.putconn(conn)


# =========================================================
# 4. ВСПОМОГАТЕЛЬНАЯ ЛОГИКА
# =========================================================
def download_file_from_s3(key, retries=3, delay=3):
    """Загрузка PDF с механизмом повторов."""
    for attempt in range(retries):
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            return obj["Body"].read()
        except s3.exceptions.NoSuchKey:
            if attempt == retries - 1: raise
            logger.warning(f"S3: Файл {key} не найден (попытка {attempt + 1})")
            time.sleep(delay)
    return None


def process_qr(qr_text, record_id, stor_url, pdf_bytes, cur):
    """Бизнес-логика разбора QR-кода."""
    if "rpismo-wsna-" in qr_text:
        match = RE_WSNA.search(qr_text)
        if not match: raise ValueError("Ошибка формата wsna")

        letter_id = int(match.group(1))
        queries.update_as_answer(cur, record_id, letter_id, stor_url)
        logger.info(f"ID {record_id}: привязан ответ к письму {letter_id}")

    elif "rpismo-answ-" in qr_text:
        match = RE_ANSW.search(qr_text)
        if not match: raise ValueError("Ошибка формата answ")

        blank_id = int(match.group(1))
        phone = ocr.extract_phone(pdf_bytes)

        if not phone:
            queries.mark_as_error(cur, record_id, stor_url, "OCR failed (no phone)", qr_text=qr_text)
            return

        success, res = queries.create_init_letter(cur, record_id, blank_id, stor_url, phone)
        if not success:
            queries.mark_as_error(cur, record_id, stor_url, res, qr_text=qr_text)
        else:
            logger.info(f"ID {record_id}: создано письмо {res} ({phone})")

    else:
        queries.mark_as_error(cur, record_id, stor_url, f"Неизвестный QR: {qr_text}", qr_text=qr_text)


# =========================================================
# 5. ОБРАБОТЧИКИ ЗАДАЧ
# =========================================================
@retry_db()
def handle_notification(payload):
    """Основной поток обработки файла."""
    start_time = time.perf_counter()
    record_id, stor_url = int(payload), "Unknown"

    try:
        with get_db() as (conn, cur):
            stor_url = queries.get_file_info(cur, record_id)
            if not stor_url:
                logger.warning(f"ID {record_id} не найден в БД")
                return

            logger.info(f">>> Старт ID {record_id}")

            pdf_bytes = download_file_from_s3(stor_url)
            qr_results = scan_pdf_qr(pdf_bytes)

            # Выбираем первый валидный результат (где r[2] == True)
            valid_qr = next((r for r in qr_results if r[2]), None)

            if not valid_qr:
                error_msg = qr_results[0][1] if qr_results else "QR не найден"
                queries.mark_as_error(cur, record_id, stor_url, f"Ошибка QR: {error_msg}")
                return

            process_qr(valid_qr[1], record_id, stor_url, pdf_bytes, cur)

        elapsed = time.perf_counter() - start_time
        logger.info(f"<<< ID {record_id} завершен за {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Ошибка при обработке ID {record_id}: {e}")
        # Попытка записать ошибку в БД (в отдельной транзакции)
        try:
            with get_db() as (_, cur):
                queries.mark_as_error(cur, record_id, stor_url, f"System error: {e}")
        except Exception:
            logger.critical("Не удалось залогировать системную ошибку в БД!")


# =========================================================
# 6. ЦИКЛЫ LISTEN И ПРОВЕРКИ
# =========================================================
def listen_notifications():
    """Слушатель PostgreSQL LISTEN/NOTIFY."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("LISTEN new_scan;")

    logger.info("Воркер активен. Ожидание уведомлений...")

    while True:
        # Ждем события 5 секунд, затем проверяем статус (select не дает процессу зависнуть)
        if select.select([conn], [], [], 5) == ([], [], []):
            continue

        conn.poll()
        while conn.notifies:
            notify = conn.notifies.pop(0)
            executor.submit(handle_notification, notify.payload)


# =========================================================
# 7. ТОЧКА ВХОДА
# =========================================================
if __name__ == "__main__":
    try:
        # 1. Сначала обрабатываем то, что уже лежит в БД
        with get_db() as (_, cur):
            pending = queries.get_pending_tasks(cur)
            if pending:
                logger.info(f"Обработка накопленной очереди: {len(pending)} задач")
                for pid in pending:
                    executor.submit(handle_notification, pid)

        # 2. Переходим в режим реального времени
        listen_notifications()

    except KeyboardInterrupt:
        logger.info("Воркер остановлен вручную")
    finally:
        logger.info("Завершение работы потоков...")
        executor.shutdown(wait=True)
        db_pool.closeall()
        logger.info("Воркер успешно выключен.")
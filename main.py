import logging
import select
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
import boto3

from config import *
import queries
from services import DocumentProcessor, StorageService
from qr_service import scan_pdf_qr
from phone_ocr import PhoneOCR

# =========================================================
# 1. КОНФИГУРАЦИЯ И ЛОГИ
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("worker.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =========================================================
# 2. ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ (Dependency Injection)
# =========================================================
try:
    # Пул соединений для многопоточности
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, **DB_CONFIG)
    logger.info("ThreadedConnectionPool успешно запущен.")
except Exception as e:
    logger.critical(f"Ошибка подключения к БД: {e}")
    exit(1)

# Создаем объекты сервисов один раз при старте
s3_client = boto3.client("s3", **S3_CONFIG)
storage = StorageService(s3_client)
# Передаем конкретные движки распознавания в процессор
processor = DocumentProcessor(ocr_engine=PhoneOCR(), qr_scanner=scan_pdf_qr)
# Пул потоков для параллельной обработки
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="WorkerThread")


# =========================================================
# 3. РАБОТА С БАЗОЙ
# =========================================================
@contextmanager
def get_db_session():
    """Менеджер транзакций: берет коннект, делает коммит или откат."""
    conn = db_pool.getconn()
    try:
        # Простая проверка на "живое" соединение
        if conn.closed != 0:
            conn = db_pool.getconn()
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        db_pool.putconn(conn)


# =========================================================
# 4. ЯДРО ОБРАБОТКИ
# =========================================================
def handle_notification(payload):
    """
    Главный сценарий обработки одного файла.
    Функция только координирует вызовы сервисов.
    """
    record_id = int(payload)
    stor_url = "Unknown"
    start_time = time.perf_counter()

    try:
        with get_db_session() as cur:
            # 1. Получаем метаданные (через queries)
            stor_url = queries.get_file_info(cur, record_id)
            if not stor_url:
                logger.warning(f"ID {record_id} не найден в таблице proc_files.")
                return

            logger.info(f"==> Начало обработки ID {record_id} ({stor_url})")

            # 2. Скачивание (через StorageService)
            pdf_bytes = storage.download(stor_url)

            # 3. Анализ документа (через DocumentProcessor)
            doc = processor.get_document_info(pdf_bytes)

            # 4. Сохранение результата (через queries)
            if doc["status"] == "error":
                queries.mark_as_error(
                    cur, record_id, stor_url,
                    reason=doc["reason"],
                    qr_text=doc.get("qr_text") or doc.get("raw")
                )
            elif doc["type"] == "answer":
                queries.update_as_answer(cur, record_id, doc["id"], stor_url)
            elif doc["type"] == "init":
                if not doc.get("phone"):
                    queries.mark_as_error(cur, record_id, stor_url, "PHONE_NOT_FOUND", qr_text=doc["qr_text"])
                else:
                    success, res = queries.create_init_letter(cur, record_id, doc["id"], stor_url, doc["phone"])
                    if not success:
                        queries.mark_as_error(cur, record_id, stor_url, res, qr_text=doc["qr_text"])

        elapsed = time.perf_counter() - start_time
        logger.info(f"<== ID {record_id} обработан за {elapsed:.2f} сек.")

    except Exception as e:
        logger.error(f"Критический сбой обработки ID {record_id}: {e}")
        # Попытка записать системную ошибку в карантин
        try:
            with get_db_session() as err_cur:
                queries.mark_as_error(err_cur, record_id, stor_url, f"System Crash: {str(e)[:100]}")
        except:
            logger.critical("Не удалось залогировать ошибку в базу данных!")


# =========================================================
# 5. ЦИКЛ ОЖИДАНИЯ И СТАРТ
# =========================================================
def run_listen_loop():
    """Слушает канал уведомлений PostgreSQL."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("LISTEN new_scan;")

    logger.info("Воркер перешел в режим ожидания (LISTEN new_scan)...")

    while True:
        # Ожидание события без блокировки процесса
        if select.select([conn], [], [], 5) == ([], [], []):
            continue

        conn.poll()
        while conn.notifies:
            notify = conn.notifies.pop(0)
            # Отдаем задачу в пул потоков
            executor.submit(handle_notification, notify.payload)


if __name__ == "__main__":
    try:
        # Первичная проверка очереди (на случай, если воркер лежал)
        with get_db_session() as main_cur:
            pending = queries.get_pending_tasks(main_cur)
            if pending:
                logger.info(f"Найдено {len(pending)} необработанных задач. Запуск...")
                for pid in pending:
                    executor.submit(handle_notification, pid)

        run_listen_loop()
    except KeyboardInterrupt:
        logger.info("Воркер остановлен пользователем.")
    finally:
        executor.shutdown(wait=True)
        db_pool.closeall()
        logger.info("Ресурсы освобождены. Работа завершена.")
import logging
import logging.config
import select
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import boto3
import psycopg2
import psycopg2.pool
from psycopg2 import DatabaseError

from config import DB_CONFIG, LOG_CONFIG, S3_CONFIG
import queries
import handlers
from services import DocumentProcessor, StorageService
from qr_service import scan_pdf_qr
from phone_ocr import PhoneOCR

# =========================================================
# 1. ЛОГИРОВАНИЕ
# =========================================================
logging.config.dictConfig(LOG_CONFIG)
logger = logging.getLogger("worker")

# =========================================================
# 2. ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ
# =========================================================
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, **DB_CONFIG)
    logger.info("ThreadedConnectionPool успешно инициализирован.")
except Exception as e:
    logger.critical(f"Не удалось запустить пул соединений: {e}")
    raise SystemExit(1) from e

storage   = StorageService(boto3.client("s3", **S3_CONFIG))
processor = DocumentProcessor(ocr_engine=PhoneOCR(), qr_scanner=scan_pdf_qr)
executor  = ThreadPoolExecutor(max_workers=4, thread_name_prefix="WorkerThread")


# =========================================================
# 3. МЕНЕДЖЕР ТРАНЗАКЦИЙ
# =========================================================
@contextmanager
def get_db_session():
    """Выдаёт курсор в рамках транзакции. Откатывает при любой ошибке."""
    conn = db_pool.getconn()
    try:
        if conn.closed != 0:
            db_pool.putconn(conn, close=True)
            conn = db_pool.getconn()

        cur = conn.cursor()
        yield cur
        conn.commit()
    except DatabaseError as e:
        conn.rollback()
        logger.error(f"Ошибка БД: {e.pgcode} — {e.pgerror}")
        raise
    except Exception:
        conn.rollback()
        logger.exception("Непредвиденная ошибка в транзакции")
        raise
    finally:
        db_pool.putconn(conn)


# =========================================================
# 4. ОБРАБОТКА ОДНОЙ ЗАДАЧИ
# =========================================================
def handle_notification(payload: str) -> None:
    record_id = int(payload)
    stor_url  = "Unknown"
    start     = time.perf_counter()

    logger.debug(f"Получена задача ID {record_id}")

    try:
        with get_db_session() as cur:
            stor_url = queries.get_file_info(cur, record_id)
            if not stor_url:
                logger.warning(f"ID {record_id}: запись не найдена в БД.")
                return

            logger.info(f"==> Старт ID {record_id} ({stor_url})")

            pdf_bytes = storage.download(stor_url)
            doc       = processor.get_document_info(pdf_bytes)
            handlers.process_document(cur, record_id, stor_url, doc)

        logger.info(f"<== ID {record_id} завершён за {time.perf_counter() - start:.2f}с")

    except DatabaseError:
        pass  # уже залогировано в get_db_session
    except Exception as e:
        logger.error(f"Критический сбой ID {record_id}: {e}")
        _try_save_error(record_id, stor_url, str(e))


def _try_save_error(record_id: int, stor_url: str, reason: str) -> None:
    """Пытается сохранить критическую ошибку в БД. Не бросает исключений."""
    try:
        with get_db_session() as cur:
            queries.mark_as_error(cur, record_id, stor_url,
                                  f"Critical: {reason[:50]}")
    except Exception:
        logger.critical(f"Не удалось сохранить ошибку ID {record_id} в БД!")


# =========================================================
# 5. LISTEN-ЦИКЛ
# =========================================================
def _on_future_done(future):
    """Callback: логирует необработанные исключения из потоков."""
    exc = future.exception()
    if exc:
        logger.error(f"Необработанное исключение в потоке: {exc}")


def run_listen_loop() -> None:
    """Слушает PostgreSQL NOTIFY с автоматическим переподключением."""
    while True:
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            cursor.execute("LISTEN new_scan;")
            logger.info("Воркер активен и слушает канал new_scan...")

            while True:
                if select.select([conn], [], [], 5) == ([], [], []):
                    continue
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    future = executor.submit(handle_notification, notify.payload)
                    future.add_done_callback(_on_future_done)

        except Exception:
            logger.exception("Потеряно соединение с БД, переподключение через 5 сек.")
            time.sleep(5)


# =========================================================
# 6. ТОЧКА ВХОДА
# =========================================================
if __name__ == "__main__":
    try:
        # Дообработка задач, оставшихся с прошлого запуска
        with get_db_session() as main_cur:
            pending = queries.get_pending_tasks(main_cur)
            if pending:
                logger.info(f"Дообработка очереди: {len(pending)} задач.")
                for pid in pending:
                    future = executor.submit(handle_notification, str(pid))
                    future.add_done_callback(_on_future_done)

        run_listen_loop()

    except KeyboardInterrupt:
        logger.info("Воркер выключен вручную.")
    finally:
        executor.shutdown(wait=True)
        db_pool.closeall()
        logger.info("Работа завершена.")
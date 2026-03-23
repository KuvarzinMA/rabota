import logging.config
import select
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool, DatabaseError
import boto3

from config import *
import queries
from services import DocumentProcessor, StorageService
from qr_service import scan_pdf_qr
from phone_ocr import PhoneOCR

# =========================================================
# 1. КОНФИГУРАЦИЯ ЛОГОВ
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
    exit(1)

storage = StorageService(boto3.client("s3", **S3_CONFIG))
processor = DocumentProcessor(ocr_engine=PhoneOCR(), qr_scanner=scan_pdf_qr)
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="WorkerThread")


# =========================================================
# 3. РАБОТА С БАЗОЙ (SQL ИСКЛЮЧЕНИЯ)
# =========================================================
@contextmanager
def get_db_session():
    """Менеджер транзакций с обработкой именно SQL ошибок."""
    conn = db_pool.getconn()
    try:
        if conn.closed != 0:
            conn = db_pool.getconn()
        cur = conn.cursor()
        yield cur
        conn.commit()
    except DatabaseError as e:
        conn.rollback()
        logger.error(f"Ошибка на уровне базы данных (SQL): {e.pgcode} - {e.pgerror}")
        raise e
    except Exception as e:
        conn.rollback()
        logger.exception("Непредвиденная системная ошибка в транзакции")
        raise e
    finally:
        db_pool.putconn(conn)


# =========================================================
# 4. ЯДРО ОБРАБОТКИ
# =========================================================
def handle_notification(payload):
    record_id = int(payload)
    stor_url = "Unknown"
    start_time = time.perf_counter()

    # DEBUG: виден только в файле логов (из-за настроек в конфиге)
    logger.debug(f"Получена задача на обработку ID {record_id}")

    try:
        with get_db_session() as cur:
            stor_url = queries.get_file_info(cur, record_id)
            if not stor_url:
                logger.warning(f"Запись ID {record_id} не найдена.")
                return

            logger.info(f"==> Старт ID {record_id} ({stor_url})")

            pdf_bytes = storage.download(stor_url)
            doc = processor.get_document_info(pdf_bytes)

            if doc["status"] == "error":
                logger.error(f"Ошибка анализа ID {record_id}: {doc['reason']}")
                queries.mark_as_error(
                    cur, record_id, stor_url,
                    reason=doc["reason"],
                    qr_text=doc.get("qr_text") or doc.get("raw")
                )
                # Статус ошибки теперь ставится внутри mark_as_error отдельной функцией

            elif doc["type"] == "answer":
                queries.update_as_answer(cur, record_id, doc["id"], stor_url)
                logger.info(f"ID {record_id}: Привязан ответ.")

            elif doc["type"] == "init":
                if not doc.get("phone"):
                    queries.mark_as_error(cur, record_id, stor_url, "PHONE_NOT_FOUND", qr_text=doc["qr_text"])
                else:
                    success, res = queries.create_init_letter(cur, record_id, doc["id"], stor_url, doc["phone"])
                    if not success:
                        queries.mark_as_error(cur, record_id, stor_url, res, qr_text=doc["qr_text"])
                    else:
                        logger.info(f"ID {record_id}: Создано письмо {res}")

        elapsed = time.perf_counter() - start_time
        logger.info(f"<== ID {record_id} успешно завершен ({elapsed:.2f} сек.)")

    except DatabaseError:
        # Ошибка БД уже залогирована в менеджере сессий
        pass
    except Exception as e:
        logger.error(f"Критический сбой ID {record_id}: {e}")
        try:
            with get_db_session() as err_cur:
                queries.mark_as_error(err_cur, record_id, stor_url, f"Critical System Error: {str(e)[:50]}")
        except:
            logger.critical("Невозможно сохранить лог ошибки в БД!")


# =========================================================
# 5. ЦИКЛ LISTEN И СТАРТ
# =========================================================
def run_listen_loop():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("LISTEN new_scan;")

    logger.info("Воркер активен и слушает канал уведомлений...")

    while True:
        if select.select([conn], [], [], 5) == ([], [], []):
            continue

        conn.poll()
        while conn.notifies:
            notify = conn.notifies.pop(0)
            executor.submit(handle_notification, notify.payload)


if __name__ == "__main__":
    try:
        with get_db_session() as main_cur:
            pending = queries.get_pending_tasks(main_cur)
            if pending:
                logger.info(f"Дообработка очереди: {len(pending)} задач.")
                for pid in pending:
                    executor.submit(handle_notification, pid)

        run_listen_loop()
    except KeyboardInterrupt:
        logger.info("Воркер выключен вручную.")
    finally:
        executor.shutdown(wait=True)
        db_pool.closeall()
        logger.info("Работа завершена.")
import psycopg2
from psycopg2 import pool
import boto3
import select
import re
import logging
import time
from datetime import datetime
from config import *
from qr_service import scan_pdf_qr
from phone_ocr import PhoneOCR

# 1. НАСТРОЙКА ЛОГИРОВАНИЯ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("worker.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 2. ПУЛ СОЕДИНЕНИЙ (чтобы не открывать коннект на каждый чих)
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
    logger.info("Пул соединений с БД запущен.")
except Exception as e:
    logger.error(f"Ошибка пула БД: {e}")
    exit(1)

# Инициализация сервисов
s3 = boto3.client('s3', **S3_CONFIG)
ocr = PhoneOCR()


def run_unknown(cur, proc_id, stor_url, reason, qr_text=None, phone=None):
    """Безопасная запись ошибки в базу"""
    logger.warning(f"В карантин (ID {proc_id}): {reason}")
    cur.execute("""
        INSERT INTO unknown_letters (stor_url, raw_qr_text, recognized_phone, error_message)
        VALUES (%s, %s, %s, %s)
    """, (stor_url, qr_text, phone, reason))
    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (PROC_ERROR, proc_id))


def run_answer(cur, proc_id, letter_id, stor_url):
    """Логика предоплаченного ответа с обновлением типа"""
    # ОБНОВЛЯЕМ И ПУТЬ, И ТИП ПИСЬМА (на TYPE_ANSWER)
    cur.execute("""
        UPDATE letters 
        SET stor_url = %s, letter_type_id = %s 
        WHERE id = %s
    """, (stor_url, TYPE_ANSWER, letter_id))

    cur.execute("""
        INSERT INTO letter_status (letter_id, i_status_id, add_date) 
        VALUES (%s, %s, %s)
    """, (letter_id, STATUS_WRITED, datetime.now()))

    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (PROC_DONE, proc_id))
    logger.info(f"Ответ привязан к письму {letter_id}, тип изменен на {TYPE_ANSWER}")


def run_init(cur, proc_id, blank_id, stor_url, pdf_bytes, qr_text):
    """Логика инициативного письма"""
    cur.execute("SELECT used FROM init_blanks WHERE id = %s", (blank_id,))
    row = cur.fetchone()
    if not row or row[0] == 1:
        return run_unknown(cur, proc_id, stor_url, f"Бланк {blank_id} занят/нет в базе", qr_text=qr_text)

    phone = ocr.extract_phone(pdf_bytes)
    if not phone:
        return run_unknown(cur, proc_id, stor_url, "OCR не нашел номер", qr_text=qr_text)

    # Создаем/получаем юзера
    cur.execute("""
        INSERT INTO users (phone) VALUES (%s) 
        ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone 
        RETURNING id
    """, (phone,))
    user_id = cur.fetchone()[0]

    # Создаем письмо (ВАЖНО: убедись, что колонка user_id есть в таблице!)
    cur.execute("""
        INSERT INTO letters (stor_url, letter_type_id, user_id) 
        VALUES (%s, %s, %s) RETURNING id
    """, (stor_url, TYPE_INIT, user_id))
    new_letter_id = cur.fetchone()[0]

    cur.execute("""
        INSERT INTO letter_status (letter_id, i_status_id, add_date) 
        VALUES (%s, %s, %s)
    """, (new_letter_id, STATUS_WRITED, datetime.now()))

    cur.execute("UPDATE init_blanks SET used = 1 WHERE id = %s", (blank_id,))
    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (PROC_DONE, proc_id))
    logger.info(f"Создано письмо {new_letter_id} для {phone}")


def handle_notification(payload):
    """Обработка с механизмом повторов и единой транзакцией"""
    conn = db_pool.getconn()
    cur = conn.cursor()
    record_id = int(payload)
    stor_url = "Unknown"

    try:
        # 1. Получаем инфо о файле
        cur.execute("SELECT stor_url FROM proc_files WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if not row: return
        stor_url = row[0]

        # 2. Попытки скачать из S3 (Retry Logic)
        pdf_bytes = None
        for attempt in range(3):
            try:
                obj = s3.get_object(Bucket=S3_BUCKET, Key=stor_url)
                pdf_bytes = obj['Body'].read()
                break
            except s3.exceptions.NoSuchKey:
                if attempt < 2:
                    logger.warning(f"Файл {stor_url} не найден, жду 3с (попытка {attempt + 1})")
                    time.sleep(3)
                else:
                    raise

        # 3. Распознавание
        qr_results = scan_pdf_qr(pdf_bytes)
        valid_qr = next((r for r in qr_results if r[2]), None)

        if not valid_qr:
            raw_text = qr_results[0][1] if qr_results else None
            run_unknown(cur, record_id, stor_url, "QR не валиден", qr_text=raw_text)
        else:
            qr_text = valid_qr[1]
            if "rpismo-wsna-" in qr_text:
                letter_id = int(re.search(r"wsna-(\d+)", qr_text).group(1))
                run_answer(cur, record_id, letter_id, stor_url)
            elif "rpismo-answ-" in qr_text:
                blank_id = int(re.search(r"answ-(\d+)", qr_text).group(1))
                run_init(cur, record_id, blank_id, stor_url, pdf_bytes, qr_text)
            else:
                run_unknown(cur, record_id, stor_url, f"Неверный формат: {qr_text}", qr_text=qr_text)

        conn.commit()  # Фиксируем ВСЕ изменения разом

    except Exception as e:
        conn.rollback()  # Откатываем ВСЁ, если была ошибка
        err_msg = str(e)
        logger.error(f"Критический сбой ID {record_id}: {err_msg}")

        # Пишем в карантин в отдельной транзакции
        try:
            err_conn = db_pool.getconn()
            err_cur = err_conn.cursor()
            run_unknown(err_cur, record_id, stor_url, f"Sys Error: {err_msg}")
            err_conn.commit()
            db_pool.putconn(err_conn)
        except:
            pass
    finally:
        db_pool.putconn(conn)


def check_pending_tasks():
    """Разгребаем очередь при старте"""
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM proc_files WHERE processed = %s", (PROC_NEW,))
    pending = [r[0] for r in cur.fetchall()]
    db_pool.putconn(conn)

    if pending:
        logger.info(f"Найдено старых задач: {len(pending)}. Начинаю разбор...")
        for pid in pending:
            handle_notification(pid)


if __name__ == "__main__":
    check_pending_tasks()

    main_conn = psycopg2.connect(**DB_CONFIG)
    main_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = main_conn.cursor()
    cursor.execute("LISTEN new_scan;")
    logger.info("Воркер активен и слушает LISTEN new_scan...")

    while True:
        if select.select([main_conn], [], [], 5) != ([], [], []):
            main_conn.poll()
            while main_conn.notifies:
                notify = main_conn.notifies.pop(0)
                handle_notification(notify.payload)
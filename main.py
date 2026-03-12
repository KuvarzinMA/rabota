import psycopg2
import boto3
import select
import re
import logging
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

# Инициализация сервисов
s3 = boto3.client('s3', **S3_CONFIG)
ocr = PhoneOCR()


def run_unknown(cur, proc_id, stor_url, reason, qr_text=None, phone=None):
    logger.warning(f"Перенос в unknown_letters (ID {proc_id}): {reason}")
    cur.execute("""
        INSERT INTO unknown_letters (stor_url, raw_qr_text, recognized_phone, error_message)
        VALUES (%s, %s, %s, %s)
    """, (stor_url, qr_text, phone, reason))
    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (PROC_ERROR, proc_id))


def run_answer(cur, proc_id, letter_id, stor_url):
    """Логика предоплаченного ответа"""
    cur.execute("""
            UPDATE letters 
            SET stor_url = %s, 
                letter_type_id = %s 
            WHERE id = %s
        """, (stor_url, TYPE_ANSWER, letter_id))
    cur.execute("""
        INSERT INTO letter_status (letter_id, i_status_id, add_date) 
        VALUES (%s, %s, %s)
    """, (letter_id, STATUS_WRITED, datetime.now()))
    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (PROC_DONE, proc_id))
    logger.info(f"Ответ привязан к письму {letter_id}")


def run_init(cur, proc_id, blank_id, stor_url, pdf_bytes, qr_text):
    cur.execute("SELECT used FROM init_blanks WHERE id = %s", (blank_id,))
    row = cur.fetchone()
    if not row or row[0] == 1:
        return run_unknown(cur, proc_id, stor_url, f"Бланк {blank_id} занят/не существует", qr_text=qr_text)

    phone = ocr.extract_phone(pdf_bytes)
    if not phone:
        return run_unknown(cur, proc_id, stor_url, "Нейросеть не распознала номер", qr_text=qr_text)

    cur.execute("""
        INSERT INTO users (phone) VALUES (%s) 
        ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone 
        RETURNING id
    """, (phone,))
    user_id = cur.fetchone()[0]

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
    """Основная логика обработки одной записи"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    stor_url = "Unknown"
    record_id = int(payload)

    try:
        cur.execute("SELECT stor_url FROM proc_files WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if not row: return
        stor_url = row[0]

        logger.info(f"Начало обработки ID {record_id} ({stor_url})")
        obj = s3.get_object(Bucket=S3_BUCKET, Key=stor_url)
        pdf_bytes = obj['Body'].read()

        qr_results = scan_pdf_qr(pdf_bytes)
        valid_qr = next((r for r in qr_results if r[2]), None)

        if not valid_qr:
            raw_text = qr_results[0][1] if qr_results else None
            run_unknown(cur, record_id, stor_url, "QR не валиден", qr_text=raw_text)
            conn.commit()
            return

        qr_text = valid_qr[1]

        if "rpismo-wsna-" in qr_text:
            letter_id = int(re.search(r"wsna-(\d+)", qr_text).group(1))
            run_answer(cur, record_id, letter_id, stor_url)
        elif "rpismo-answ-" in qr_text:
            blank_id = int(re.search(r"answ-(\d+)", qr_text).group(1))
            run_init(cur, record_id, blank_id, stor_url, pdf_bytes, qr_text)
        else:
            run_unknown(cur, record_id, stor_url, f"Тип QR не ясен: {qr_text}", qr_text=qr_text)

        conn.commit()

    except Exception as e:
        conn.rollback()
        err_msg = str(e)
        logger.error(f"Сбой ID {record_id}: {err_msg}")
        try:
            err_conn = psycopg2.connect(**DB_CONFIG)
            run_unknown(err_conn.cursor(), record_id, stor_url, f"System Error: {err_msg}")
            err_conn.commit()
            err_conn.close()
        except:
            pass
    finally:
        conn.close()


def check_pending_tasks():
    """ЗАЩИТА ОТ ПЕРЕЗАГРУЗКИ: проверяем, что осталось в очереди"""
    logger.info("Проверка необработанных задач в базе...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT id FROM proc_files WHERE processed = %s", (PROC_NEW,))
    pending = cur.fetchall()
    conn.close()

    if pending:
        logger.info(f"Найдено пропущенных задач: {len(pending)}")
        for (pid,) in pending:
            handle_notification(pid)
    else:
        logger.info("Очередь пуста, засыпаю.")


if __name__ == "__main__":
    # Сначала разгребаем то, что накопилось пока мы были выключены
    check_pending_tasks()

    # Теперь входим в режим ожидания новых сигналов
    main_conn = psycopg2.connect(**DB_CONFIG)
    main_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = main_conn.cursor()
    cursor.execute("LISTEN new_scan;")
    logger.info("Воркер перешел в режим LISTEN.")

    while True:
        if select.select([main_conn], [], [], 5) != ([], [], []):
            main_conn.poll()
            while main_conn.notifies:
                notify = main_conn.notifies.pop(0)
                handle_notification(notify.payload)
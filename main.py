import psycopg2
import boto3
import select
import re
import json
from datetime import datetime
from config import *
from qr_service import scan_pdf_qr
from phone_ocr import PhoneOCR

# Инициализация сервисов
s3 = boto3.client('s3', **S3_CONFIG)
ocr = PhoneOCR()


def handle_notification(payload):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        record_id = int(payload)
        # Получаем путь к файлу
        cur.execute("SELECT stor_url FROM proc_files WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if not row: return
        stor_url = row[0]

        # 1. Загрузка из S3
        print(f"[{record_id}] Обработка файла: {stor_url}")
        obj = s3.get_object(Bucket=S3_BUCKET, Key=stor_url)
        pdf_bytes = obj['Body'].read()

        # 2. Распознавание QR
        qr_results = scan_pdf_qr(pdf_bytes)
        # Ищем первый валидный QR с контрольной суммой
        valid_qr = next((r for r in qr_results if r[2]), None)

        if not valid_qr:
            return run_unknown(cur, record_id, stor_url, "QR не найден или КС неверна")

        qr_text = valid_qr[1]

        # 3. Распределение по типам
        if "rpismo-wsna-" in qr_text:
            # Предоплаченный ответ (answer)
            letter_id = int(re.search(r"wsna-(\d+)", qr_text).group(1))
            run_answer(cur, record_id, letter_id, stor_url)

        elif "rpismo-answ-" in qr_text:
            # Инициативное письмо (init)
            blank_id = int(re.search(r"answ-(\d+)", qr_text).group(1))
            run_init(cur, record_id, blank_id, stor_url, pdf_bytes)

        else:
            run_unknown(cur, record_id, stor_url, f"Неизвестный формат QR: {qr_text}")

        conn.commit()
    except Exception as e:
        print(f"Ошибка при обработке ID {payload}: {e}")
        conn.rollback()
    finally:
        conn.close()


def run_answer(cur, proc_id, letter_id, stor_url):
    """Логика предоплаченного ответа"""
    # Обновляем путь в существующем письме
    cur.execute("UPDATE letters SET stor_url = %s WHERE id = %s", (stor_url, letter_id))

    # Ставим статус "Написан, не прочитан"
    cur.execute("""
        INSERT INTO letter_status (letter_id, i_status_id, add_date) 
        VALUES (%s, %s, %s)
    """, (letter_id, STATUS_WRITED, datetime.now()))

    # Помечаем файл как обработанный
    cur.execute("UPDATE proc_files SET processed = 1 WHERE id = %s", (proc_id,))

    # Получаем данные пользователя для уведомления (если нужно)
    cur.execute("""
        SELECT u.phone, u.email FROM users u 
        JOIN letters l ON l.id = %s -- тут логика связи зависит от твоей структуры
        LIMIT 1
    """, (letter_id,))
    print(f"Ответ привязан к письму {letter_id}. Статус: writed.")


def run_init(cur, proc_id, blank_id, stor_url, pdf_bytes):
    """Логика инициативного письма"""
    # Проверка бланка
    cur.execute("SELECT used FROM init_blanks WHERE id = %s", (blank_id,))
    row = cur.fetchone()
    if not row or row[0] == 1:
        print(f"Бланк {blank_id} уже использован или не существует. Пропуск.")
        return

    # Распознаем номер телефона нейронкой
    phone = ocr.extract_phone(pdf_bytes)
    if not phone:
        return run_unknown(cur, proc_id, stor_url, "Нейросеть не распознала номер")

    # Создаем/получаем пользователя
    cur.execute("""
        INSERT INTO users (phone) VALUES (%s) 
        ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone 
        RETURNING id
    """, (phone,))
    user_id = cur.fetchone()[0]

    # Создаем новое письмо типа "init" (id=1)
    cur.execute("""
        INSERT INTO letters (stor_url, letter_type_id) 
        VALUES (%s, %s) RETURNING id
    """, (stor_url, TYPE_INIT))
    new_letter_id = cur.fetchone()[0]

    # Проставляем статус
    cur.execute("""
        INSERT INTO letter_status (letter_id, i_status_id, add_date) 
        VALUES (%s, %s, %s)
    """, (new_letter_id, STATUS_WRITED, datetime.now()))

    # Помечаем бланк как использованный и файл как обработанный
    cur.execute("UPDATE init_blanks SET used = 1 WHERE id = %s", (blank_id,))
    cur.execute("UPDATE proc_files SET processed = 1 WHERE id = %s", (proc_id,))
    print(f"Создано инициативное письмо {new_letter_id} для номера {phone}")


def run_unknown(cur, proc_id, stor_url, reason):
    """Логика для ошибок и неизвестных сканов"""
    # Если нет таблицы unknown_letters, можно писать в лог или спец. статус
    print(f"UNKNOWN SCAN: {reason}")
    cur.execute("UPDATE proc_files SET processed = -1 WHERE id = %s", (proc_id,))


if __name__ == "__main__":
    # Основной цикл LISTEN
    main_conn = psycopg2.connect(**DB_CONFIG)
    main_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = main_conn.cursor()
    cursor.execute("LISTEN new_scan;")
    print("Воркер активен. Жду уведомлений...")

    while True:
        if select.select([main_conn], [], [], 5) != ([], [], []):
            main_conn.poll()
            while main_conn.notifies:
                notify = main_conn.notifies.pop(0)
                handle_notification(notify.payload)
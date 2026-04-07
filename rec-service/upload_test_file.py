import os
import boto3
import psycopg2
from config import DB_CONFIG, S3_CONFIG, S3_BUCKET, PROC_NEW


def upload_and_notify(file_path: str):
    file_name = os.path.basename(file_path)
    # 1. Загружаем файл в S3
    try:
        s3_client = boto3.client("s3", **S3_CONFIG)
        # Путь в бакете, например: 2026/03/filename.pdf
        s3_key = f"{file_name}"

        print(f"Загрузка {file_name} в S3...")
        s3_client.upload_file(file_path, S3_BUCKET, s3_key)
        print(f"Файл загружен в S3: {s3_key}")
    except Exception as e:
        print(f"Ошибка S3: {e}")
        return

    # 2. Создаем запись в Postgres и отправляем NOTIFY
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Вставляем запись в таблицу очереди
        # Указываем статус PROC_NEW (обычно 0)
        query = """
            INSERT INTO proc_files (stor_url, processed) 
            VALUES (%s, %s) 
            RETURNING id;
        """
        cur.execute(query, (s3_key, PROC_NEW))
        new_id = cur.fetchone()[0]

        # отправляем сигнал воркеру
        cur.execute(f"NOTIFY new_scan, '{new_id}';")

        conn.commit()
        print(f"Запись создана в БД (ID: {new_id}), сигнал NOTIFY отправлен.")

    except Exception as e:
        print(f"Ошибка БД: {e}")
    finally:
        if conn:
            cur.close()
            conn.close()


if __name__ == "__main__":
    TEST_FILE = "../number-recognition/scan_20260406152358.pdf"

    if os.path.exists(TEST_FILE):
        upload_and_notify(TEST_FILE)
    else:
        print(f"Создай файл {TEST_FILE} для теста.")
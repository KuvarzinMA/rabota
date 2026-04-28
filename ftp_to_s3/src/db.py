import psycopg2
from psycopg2.extras import execute_values

from src.config import DB_CONFIG, DB_NOTIFY_CHANNEL, PROC_NEW
from src.logger import log


# Отдельная миграция — добавляет constraint если его нет.
_MIGRATE_UNIQUE = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'proc_files_s3_bucket_s3_key_key'
          AND conrelid = 'proc_files'::regclass
    ) THEN
        ALTER TABLE proc_files
            ADD CONSTRAINT proc_files_s3_bucket_s3_key_key
            UNIQUE (s3_bucket, s3_key);
    END IF;
END;
$$;
"""


def ensure_table() -> None:
    _exec(_MIGRATE_UNIQUE, commit=True)
    log.info("БД: таблица proc_files готова")


def register_files(s3_keys: list[str], s3_bucket: str) -> int:
    if not s3_keys:
        return 0

    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()

        insert_sql = """
            INSERT INTO proc_files (processed, s3_key, s3_bucket)
            VALUES %s
            ON CONFLICT (s3_bucket, s3_key) DO NOTHING
            RETURNING id;
        """
        execute_values(
            cur,
            insert_sql,
            [(PROC_NEW, key, s3_bucket) for key in s3_keys],
        )
        rows = cur.fetchall()
        inserted = len(rows)

        # NOTIFY в той же транзакции — воркер получит сигнал только после COMMIT
        for (new_id,) in rows:
            cur.execute(
                f"NOTIFY {DB_NOTIFY_CHANNEL}, %s;",
                (str(new_id),),
            )
            log.debug(f"  NOTIFY {DB_NOTIFY_CHANNEL} → id={new_id}")

        conn.commit()

        if inserted:
            log.info(
                f"  БД [{s3_bucket}]: зарегистрировано {inserted} файлов, "
                f"NOTIFY отправлен"
            )
        else:
            log.debug(f"  БД [{s3_bucket}]: все файлы уже зарегистрированы")

    except Exception as exc:
        log.error(f"  БД ошибка [{s3_bucket}]: {exc}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

    return inserted


def _exec(sql: str, commit: bool = False) -> None:
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute(sql)
        if commit:
            conn.commit()
    finally:
        if conn:
            cur.close()
            conn.close()

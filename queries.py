import psycopg2
from psycopg2 import errors
from datetime import datetime
from config import PROC_DONE, PROC_ERROR, TYPE_INIT, TYPE_ANSWER, STATUS_WRITED


def update_proc_status(cur, record_id, status):
    """Отдельная атомарная функция для управления жизненным циклом задачи."""
    try:
        cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (status, record_id))
    except psycopg2.Error as e:
        # Логируем специфический код ошибки Postgres (e.pgcode)
        raise RuntimeError(f"SQL Status Update Error: {e.pgcode}")


def get_file_info(cur, record_id):
    cur.execute("SELECT stor_url FROM proc_files WHERE id = %s", (record_id,))
    row = cur.fetchone()
    return row[0] if row else None


def get_or_create_user(cur, phone):
    """Использование UPSERT для обеспечения идемпотентности."""
    cur.execute("""
        INSERT INTO users (phone) VALUES (%s) 
        ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone 
        RETURNING id
    """, (phone,))
    return cur.fetchone()[0]


def reserve_blank(cur, blank_id):
    cur.execute("SELECT used FROM init_blanks WHERE id = %s FOR UPDATE", (blank_id,))
    row = cur.fetchone()
    if not row or row[0] == 1:
        return False
    cur.execute("UPDATE init_blanks SET used = 1 WHERE id = %s", (blank_id,))
    return True


def create_init_letter(cur, record_id, blank_id, stor_url, phone):
    """Сборка инициативного письма из кирпичиков."""
    if not reserve_blank(cur, blank_id):
        return False, "Бланк занят"

    user_id = get_or_create_user(cur, phone)

    cur.execute("""
        INSERT INTO letters (stor_url, letter_type_id, user_id) 
        VALUES (%s, %s, %s) RETURNING id
    """, (stor_url, TYPE_INIT, user_id))

    new_id = cur.fetchone()[0]
    update_proc_status(cur, record_id, PROC_DONE)
    return True, new_id


def mark_as_error(cur, record_id, stor_url, reason, qr_text=None):
    """Карантин для проблемных файлов."""
    cur.execute("""
        INSERT INTO unknown_letters (stor_url, raw_qr_text, error_message)
        VALUES (%s, %s, %s)
    """, (stor_url, qr_text, reason))
    update_proc_status(cur, record_id, PROC_ERROR)
from datetime import datetime
from config import TYPE_INIT, TYPE_ANSWER, STATUS_WRITED, PROC_DONE, PROC_ERROR


def get_pending_tasks(cur):
    """Получает список всех необработанных ID"""
    cur.execute("SELECT id FROM proc_files WHERE processed = 0")
    return [r[0] for r in cur.fetchall()]


def get_file_info(cur, record_id):
    """Получает путь к файлу в S3 по ID записи"""
    cur.execute("SELECT stor_url FROM proc_files WHERE id = %s", (record_id,))
    row = cur.fetchone()
    return row[0] if row else None


def mark_as_error(cur, proc_id, stor_url, reason, qr_text=None, phone=None):
    """Записывает ошибку и переносит в карантин"""
    cur.execute("""
        INSERT INTO unknown_letters (stor_url, raw_qr_text, recognized_phone, error_message)
        VALUES (%s, %s, %s, %s)
    """, (stor_url, qr_text, phone, reason))
    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (PROC_ERROR, proc_id))


def update_as_answer(cur, proc_id, letter_id, stor_url):
    """Обновляет письмо как ответ (тип 2)"""
    cur.execute("""
        UPDATE letters 
        SET stor_url = %s, letter_type_id = %s 
        WHERE id = %s
    """, (stor_url, TYPE_ANSWER, letter_id))

    _add_letter_status(cur, letter_id, STATUS_WRITED)
    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (PROC_DONE, proc_id))


def create_init_letter(cur, proc_id, blank_id, stor_url, phone):
    """Создает новое инициативное письмо (тип 1)"""
    # 1. Проверка бланка
    cur.execute("SELECT used FROM init_blanks WHERE id = %s", (blank_id,))
    row = cur.fetchone()
    if not row or row[0] == 1:
        return False, f"Бланк {blank_id} занят или отсутствует"

    # 2. Юзер
    cur.execute("""
        INSERT INTO users (phone) VALUES (%s) 
        ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone 
        RETURNING id
    """, (phone,))
    user_id = cur.fetchone()[0]

    # 3. Письмо
    cur.execute("""
        INSERT INTO letters (stor_url, letter_type_id, user_id) 
        VALUES (%s, %s, %s) RETURNING id
    """, (stor_url, TYPE_INIT, user_id))
    new_letter_id = cur.fetchone()[0]

    # 4. Статус и финализация
    _add_letter_status(cur, new_letter_id, STATUS_WRITED)
    cur.execute("UPDATE init_blanks SET used = 1 WHERE id = %s", (blank_id,))
    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (PROC_DONE, proc_id))

    return True, new_letter_id


def _add_letter_status(cur, letter_id, status_id):
    """Внутренняя вспомогательная функция для добавления статуса"""
    cur.execute("""
        INSERT INTO letter_status (letter_id, i_status_id, add_date) 
        VALUES (%s, %s, %s)
    """, (letter_id, status_id, datetime.now()))
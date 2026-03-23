from datetime import datetime
from config import TYPE_INIT, TYPE_ANSWER, STATUS_WRITED, PROC_DONE, PROC_ERROR


# --- 1. МАЛЕНЬКИЕ АТОМАРНЫЕ ФУНКЦИИ (Building Blocks) ---

def get_file_info(cur, record_id):
    """Только получение пути к файлу"""
    cur.execute("SELECT stor_url FROM proc_files WHERE id = %s", (record_id,))
    row = cur.fetchone()
    return row[0] if row else None


def get_or_create_user(cur, phone):
    """Только работа с личностью пользователя"""
    cur.execute("""
        INSERT INTO users (phone) VALUES (%s) 
        ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone 
        RETURNING id
    """, (phone,))
    return cur.fetchone()[0]


def reserve_blank(cur, blank_id):
    """Только проверка и блокировка бланка"""
    # FOR UPDATE блокирует строку, чтобы два воркера не схватили один бланк
    cur.execute("SELECT used FROM init_blanks WHERE id = %s FOR UPDATE", (blank_id,))
    row = cur.fetchone()
    if not row or row[0] == 1:
        return False
    cur.execute("UPDATE init_blanks SET used = 1 WHERE id = %s", (blank_id,))
    return True


def set_proc_status(cur, proc_id, status):
    """Только обновление очереди обработки"""
    cur.execute("UPDATE proc_files SET processed = %s WHERE id = %s", (status, proc_id))


def add_letter_status(cur, letter_id, status_id):
    """Только запись в историю статусов письма"""
    cur.execute("""
        INSERT INTO letter_status (letter_id, i_status_id, add_date) 
        VALUES (%s, %s, %s)
    """, (letter_id, status_id, datetime.now()))


# --- 2. БИЗНЕС-ЛОГИКА (Оркестрация действий) ---

def create_init_letter(cur, proc_id, blank_id, stor_url, phone):
    """Создание нового письма (Тип 1)"""
    # Используем атомарные функции
    if not reserve_blank(cur, blank_id):
        return False, f"Бланк {blank_id} уже использован или не существует"

    user_id = get_or_create_user(cur, phone)

    cur.execute("""
        INSERT INTO letters (stor_url, letter_type_id, user_id) 
        VALUES (%s, %s, %s) RETURNING id
    """, (stor_url, TYPE_INIT, user_id))
    new_id = cur.fetchone()[0]

    # Финализация
    add_letter_status(cur, new_id, STATUS_WRITED)
    set_proc_status(cur, proc_id, PROC_DONE)
    return True, new_id


def update_as_answer(cur, proc_id, letter_id, stor_url):
    """Привязка скана как ответа (Тип 2)"""
    cur.execute("""
        UPDATE letters 
        SET stor_url = %s, letter_type_id = %s 
        WHERE id = %s
    """, (stor_url, TYPE_ANSWER, letter_id))

    add_letter_status(cur, letter_id, STATUS_WRITED)
    set_proc_status(cur, proc_id, PROC_DONE)


def mark_as_error(cur, proc_id, stor_url, reason, qr_text=None, phone=None):
    """Логирование ошибки в карантин"""
    cur.execute("""
        INSERT INTO unknown_letters (stor_url, raw_qr_text, recognized_phone, error_message)
        VALUES (%s, %s, %s, %s)
    """, (stor_url, qr_text, phone, reason))

    set_proc_status(cur, proc_id, PROC_ERROR)


def get_pending_tasks(cur):
    """Получение списка задач для доработки"""
    cur.execute("SELECT id FROM proc_files WHERE processed = 0")
    return [r[0] for r in cur.fetchall()]
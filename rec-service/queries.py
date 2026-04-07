import psycopg2
from config import PROC_DONE, PROC_ERROR, TYPE_INIT


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ
# =========================================================

def update_proc_status(cur, record_id: int, status: int) -> None:
    """Обновляет статус обработки файла."""
    try:
        cur.execute(
            "UPDATE proc_files SET processed = %s WHERE id = %s",
            (status, record_id),
        )
    except psycopg2.Error as e:
        raise RuntimeError(f"SQL Status Update Error: {e.pgcode}") from e


def get_file_info(cur, record_id: int) -> str | None:
    """Возвращает stor_url по ID записи, или None если не найдена."""
    cur.execute("SELECT stor_url FROM proc_files WHERE id = %s", (record_id,))
    row = cur.fetchone()
    return row[0] if row else None


def get_pending_tasks(cur) -> list[int]:
    """Возвращает ID записей, которые ещё не обработаны."""
    from config import PROC_NEW
    cur.execute("SELECT id FROM proc_files WHERE processed = %s", (PROC_NEW,))
    return [row[0] for row in cur.fetchall()]


# =========================================================
# ПОЛЬЗОВАТЕЛИ
# =========================================================

def get_or_create_user(cur, phone: str) -> int:
    """UPSERT пользователя по номеру телефона, возвращает его ID."""
    cur.execute(
        """
        INSERT INTO users (phone) VALUES (%s)
        ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone
        RETURNING id
        """,
        (phone,),
    )
    return cur.fetchone()[0]


# =========================================================
# БЛАНКИ
# =========================================================

def reserve_blank(cur, blank_id: int) -> bool:
    """Атомарно резервирует бланк через SELECT FOR UPDATE. Возвращает False если занят."""
    cur.execute(
        "SELECT used FROM init_blanks WHERE id = %s FOR UPDATE",
        (blank_id,),
    )
    row = cur.fetchone()
    if not row or row[0] == 1:
        return False
    cur.execute("UPDATE init_blanks SET used = 1 WHERE id = %s", (blank_id,))
    return True


# =========================================================
# ПИСЬМА
# =========================================================

def create_init_letter(cur, record_id: int, blank_id: int, stor_url: str, phone: str) -> tuple[bool, str | int]:
    """
    Создаёт инициативное письмо.
    Возвращает (True, new_letter_id) или (False, причина_ошибки).
    """
    if not reserve_blank(cur, blank_id):
        return False, "BLANK_ALREADY_USED"

    user_id = get_or_create_user(cur, phone)

    cur.execute(
        """
        INSERT INTO letters (stor_url, letter_type_id, user_id)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (stor_url, TYPE_INIT, user_id),
    )
    new_id = cur.fetchone()[0]
    update_proc_status(cur, record_id, PROC_DONE)
    return True, new_id


def update_as_answer(cur, record_id: int, letter_id: int, stor_url: str) -> None:
    """Привязывает скан как ответ к существующему письму."""
    cur.execute(
        "UPDATE letters SET answer_stor_url = %s WHERE id = %s",
        (stor_url, letter_id),
    )
    update_proc_status(cur, record_id, PROC_DONE)


def mark_as_error(cur, record_id: int, stor_url: str, reason: str, qr_text: str | None = None) -> None:
    """Помещает файл в карантин и проставляет статус ошибки."""
    cur.execute(
        """
        INSERT INTO unknown_letters (stor_url, raw_qr_text, error_message)
        VALUES (%s, %s, %s)
        """,
        (stor_url, qr_text, reason),
    )
    update_proc_status(cur, record_id, PROC_ERROR)
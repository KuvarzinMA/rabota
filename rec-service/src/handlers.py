import logging

import src.queries

logger = logging.getLogger("worker.handlers")

# Причины которые не идут в unknown_letters — только лог
_SKIP_QUARANTINE = {"BLANK_ALREADY_USED"}


def process_document(cur, record_id: int, stor_url: str, doc: dict) -> None:
    """
    Точка входа для обработки одного документа.
    Маршрутизирует по типу и статусу, не бросает исключений наружу.
    """
    if doc["status"] == "error":
        logger.error(f"ID {record_id}: ошибка анализа — {doc['reason']}")
        queries.mark_as_error(
            cur, record_id, stor_url,
            reason=doc["reason"],
            qr_text=doc.get("qr_text"),
        )
        return

    dispatch = {
        "answer": _handle_answer,
        "init":   _handle_init,
    }
    handler = dispatch.get(doc["type"])

    if handler is None:
        logger.error(f"ID {record_id}: неизвестный тип документа — {doc['type']!r}")
        queries.mark_as_error(cur, record_id, stor_url, "UNKNOWN_DOC_TYPE",
                              qr_text=doc.get("qr_text"))
        return

    handler(cur, record_id, stor_url, doc)


# =========================================================
# ВНУТРЕННИЕ ОБРАБОТЧИКИ
# =========================================================

def _handle_answer(cur, record_id: int, stor_url: str, doc: dict) -> None:
    """Привязывает скан как ответ к существующему письму."""
    queries.update_as_answer(cur, record_id, doc["id"], stor_url)
    logger.info(f"ID {record_id}: привязан ответ к письму {doc['id']}.")


def _handle_init(cur, record_id: int, stor_url: str, doc: dict) -> None:
    """Создаёт инициативное письмо."""
    if not doc.get("phone"):
        logger.warning(f"ID {record_id}: телефон не распознан.")
        queries.mark_as_error(cur, record_id, stor_url,
                              "PHONE_NOT_FOUND", qr_text=doc.get("qr_text"))
        return

    success, res = queries.create_init_letter(
        cur, record_id, doc["id"], stor_url, doc["phone"]
    )
    if not success:
        if res in _SKIP_QUARANTINE:
            logger.warning(f"ID {record_id}: {res} — пропускаем, в карантин не пишем.")
            queries.update_proc_status(cur, record_id, queries.PROC_DONE)
        else:
            logger.error(f"ID {record_id}: не удалось создать письмо — {res}. Отправляем в карантин.")
            queries.mark_as_error(cur, record_id, stor_url, res,
                                  qr_text=doc.get("qr_text"))
    else:
        logger.info(f"ID {record_id}: создано письмо {res} с номером {doc['phone']}")
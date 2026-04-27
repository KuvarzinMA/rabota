"""Настройка логирования."""

import logging
from pathlib import Path


LOG_FILE = Path("ftp_to_s3.log")


def setup_logger(name: str = "ftp_to_s3") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # Уже настроен (защита от двойной инициализации)

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Консоль — INFO и выше
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    # Файл — DEBUG и выше
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger


log = setup_logger()

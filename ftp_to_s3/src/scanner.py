"""
Обход дерева FTP_ROOT и сбор папок принтеров.

Структура FTP:
    FTP_ROOT/
      <printer_id>/        ← папка принтера (имя = его ID)
        scan001.pdf
        scan002.tif
"""

from pathlib import Path
from src.config import FTP_ROOT
from src.logger import log


def iter_printers(ftp_root: Path = FTP_ROOT):
    """
    Генератор: yields printer_dir: Path

    Каждая директория первого уровня считается отдельным принтером.
    Имя папки используется как printer_id и как суффикс бакета S3.
    """
    if not ftp_root.exists():
        log.error(f"Корневая папка не найдена: {ftp_root.resolve()}")
        return

    for printer_dir in sorted(ftp_root.iterdir()):
        if not printer_dir.is_dir():
            continue
        log.info(f"🖨️  Принтер: {printer_dir.name}")
        yield printer_dir

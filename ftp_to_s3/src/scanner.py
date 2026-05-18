from pathlib import Path
from src.config import FTP_ROOT
from src.logger import log


def iter_printers(ftp_root: Path = FTP_ROOT):
    if not ftp_root.exists():
        log.error(f"Корневая папка не найдена: {ftp_root.resolve()}")
        return

    for printer_dir in sorted(ftp_root.iterdir()):
        if not printer_dir.is_dir():
            continue
        log.info(f"  Принтер: {printer_dir.name}")
        yield printer_dir

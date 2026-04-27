"""
Обход дерева FTP_ROOT и сбор пар (region_dir, inst_dir).
"""

from pathlib import Path
from src.config import FTP_ROOT
from src.logger import log


def iter_institutions(ftp_root: Path = FTP_ROOT):
    """
    Генератор: yields (region: str, inst_dir: Path)

    Ожидаемая структура:
        FTP_ROOT/
          <регион>/
            <учреждение>/
              scan1.pdf
              scan2.tif
    """
    if not ftp_root.exists():
        log.error(f"Корневая папка не найдена: {ftp_root.resolve()}")
        return

    for region_dir in sorted(ftp_root.iterdir()):
        if not region_dir.is_dir():
            continue
        log.info(f"Регион: {region_dir.name}")

        for inst_dir in sorted(region_dir.iterdir()):
            if not inst_dir.is_dir():
                continue
            yield region_dir.name, inst_dir

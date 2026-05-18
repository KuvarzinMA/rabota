import configparser
import os
from typing import Union, Type
from pathlib import Path

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "settings.ini")

if not config.read(config_path, encoding="utf-8"):
    raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")


def _get(section: str, key: str, data_type: Type = str) -> Union[str, int, bool]:
    """
    Универсальный забор данных из конфига с приведением типов и обработкой ошибок.
    """
    try:
        if data_type is int:
            return config.getint(section, key)
        if data_type is bool:
            return config.getboolean(section, key)
        return config.get(section, key)

    except (configparser.NoSectionError, configparser.NoOptionError):
        raise RuntimeError(f"Ошибка: В settings.ini отсутствует [{section}] -> {key}")
    except ValueError:
        raise RuntimeError(f"Ошибка типа: Параметр [{section}] -> {key} должен быть {data_type.__name__}")


# ── Источник ──────────────────────────────────────────────────────────────────

FTP_ROOT = Path(_get("Source", "ftp_root", str))
MIN_FILE_AGE = _get("Source", "min_file_age", str)

# Парсим расширения из строки (удаляем пробелы и собираем в set)
_raw_extensions = _get("Source", "scan_extensions", str)
SCAN_EXTENSIONS = {ext.strip() for ext in _raw_extensions.split(",") if ext.strip()}

# ── S3 / rclone ───────────────────────────────────────────────────────────────

S3_REMOTE = _get("S3", "s3_remote", str)
S3_BUCKET_PREFIX = _get("S3", "s3_bucket_prefix", str)
AWS_REGION = _get("S3", "aws_region", str)

# ── Параметры rclone ──────────────────────────────────────────────────────────

RCLONE_FLAGS: list[str] = [
    "--transfers",         str(_get("Rclone", "transfers", int)),
    "--checkers",          str(_get("Rclone", "checkers", int)),
    "--retries",           "3",
    "--low-level-retries", "10",
    "--stats",             "30s",
    "--log-level",         "INFO",
    "--inplace",
    "--s3-no-check-bucket",
]

# Добавляем --dry-run, если флаг включен в конфиге
if _get("Rclone", "dry_run", bool):
    RCLONE_FLAGS.append("--dry-run")

# ── Включения файлов для rclone ───────────────────────────────────────────────

RCLONE_INCLUDE: list[str] = [
    arg
    for ext in SCAN_EXTENSIONS
    for arg in ("--include", f"*{ext}")
]

# ── PostgreSQL ────────────────────────────────────────────────────────────────

DB_CONFIG: dict = {
    "host":     _get("Database", "host", str),
    "port":     _get("Database", "port", int),
    "dbname":   _get("Database", "dbname", str),
    "user":     _get("Database", "user", str),
    "password": _get("Database", "password", str),
}

DB_NOTIFY_CHANNEL = _get("Database", "notify_channel", str)
PROC_NEW = 0

# ── Планировщик ───────────────────────────────────────────────────────────────

SCHEDULER_INTERVAL_SEC = _get("Scheduler", "interval_sec", int)
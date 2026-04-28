import configparser
import os
from typing import Union, Type
from src.log_config import build_log_config

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "settings.ini")

if not config.read(config_path):
    raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")


def _get(section: str, key: str, data_type: Type = str) -> Union[str, int, bool]:
    """
    Универсальный забор данных из конфига с приведением типов и обработкой ошибок.
    """
    try:
        if isinstance(data_type, int):
            return config.getint(section, key)
        if isinstance(data_type, bool):
            return config.getboolean(section, key)
        return config.get(section, key)

    except (configparser.NoSectionError, configparser.NoOptionError):
        raise RuntimeError(f"Ошибка: В settings.ini отсутствует [{section}] -> {key}")
    except ValueError:
        raise RuntimeError(f"Ошибка типа: Параметр [{section}] -> {key} должен быть {data_type.__name__}")


# --- База данных ---
DB_CONFIG = {
    "host":     _get("database", "host"),
    "database": _get("database", "database"),
    "user":     _get("database", "user"),
    "password": _get("database", "password"),
}

# --- S3 / MinIO ---
S3_CONFIG = {
    "endpoint_url":          _get("s3", "endpoint_url"),
    "aws_access_key_id":     _get("s3", "aws_access_key_id"),
    "aws_secret_access_key": _get("s3", "aws_secret_access_key"),
}

# --- Пути и секреты ---
MODEL_PATH = _get("paths", "model_path")
QR_SECRET  = _get("paths", "qr_secret")

# --- ID типов писем ---
TYPE_INIT    = _get("letter_types", "init")
TYPE_ANSWER  = _get("letter_types", "answer")
TYPE_FORWARD = _get("letter_types", "forward")

# --- ID статусов письма ---
STATUS_CLEAN     = _get("statuses", "clean")
STATUS_WRITED    = _get("statuses", "writed")
STATUS_READED    = _get("statuses", "readed")
STATUS_FOR_PRINT = _get("statuses", "for_print")
STATUS_PRINTED   = _get("statuses", "printed")

# --- Статусы обработки файла ---
PROC_NEW   = _get("proc_status", "new")
PROC_DONE  = _get("proc_status", "done")
PROC_ERROR = _get("proc_status", "error")

# --- Логирование ---
LOG_CONFIG = build_log_config(config)
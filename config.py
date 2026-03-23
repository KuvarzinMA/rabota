import configparser
import os

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "settings.ini")

if not config.read(config_path):
    raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")


def _get(section: str, key: str, **kwargs) -> str:
    try:
        return config.get(section, key, **kwargs)
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        raise RuntimeError(f"Отсутствует параметр в конфиге: [{section}] {key}") from e


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
S3_BUCKET = _get("s3", "bucket_name")

# --- Пути и секреты ---
MODEL_PATH = _get("paths", "model_path")
QR_SECRET  = _get("paths", "qr_secret")

# --- ID типов писем ---
TYPE_INIT    = config.getint("letter_types", "init")
TYPE_ANSWER  = config.getint("letter_types", "answer")
TYPE_FORWARD = config.getint("letter_types", "forward")

# --- ID статусов письма ---
STATUS_CLEAN     = config.getint("statuses", "clean")
STATUS_WRITED    = config.getint("statuses", "writed")
STATUS_READED    = config.getint("statuses", "readed")
STATUS_FOR_PRINT = config.getint("statuses", "for_print")
STATUS_PRINTED   = config.getint("statuses", "printed")

# --- Статусы обработки файла ---
PROC_NEW   = config.getint("proc_status", "new")
PROC_DONE  = config.getint("proc_status", "done")
PROC_ERROR = config.getint("proc_status", "error")

# --- Логирование ---
from log_config import build_log_config
LOG_CONFIG = build_log_config(config)
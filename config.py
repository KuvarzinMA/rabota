import configparser
import os

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'settings.ini')
config.read(config_path)

# --- Параметры базы данных ---
DB_CONFIG = {
    "host": config.get("database", "host"),
    "database": config.get("database", "database"),
    "user": config.get("database", "user"),
    "password": config.get("database", "password")
}

# --- Параметры S3 (MinIO) ---
S3_CONFIG = {
    "endpoint_url": config.get("s3", "endpoint_url"),
    "aws_access_key_id": config.get("s3", "aws_access_key_id"),
    "aws_secret_access_key": config.get("s3", "aws_secret_access_key"),
}
S3_BUCKET = config.get("s3", "bucket_name")

# --- Пути и секреты ---
MODEL_PATH = config.get("paths", "model_path")
QR_SECRET = config.get("paths", "qr_secret")

# --- ID Типов писем ---
TYPE_INIT = config.getint("letter_types", "init")
TYPE_ANSWER = config.getint("letter_types", "answer")
TYPE_FORWARD = config.getint("letter_types", "forward")

# --- ID Статусов ---
STATUS_CLEAN = config.getint("statuses", "clean")
STATUS_WRITED = config.getint("statuses", "writed")
STATUS_READED = config.getint("statuses", "readed")
STATUS_FOR_PRINT = config.getint("statuses", "for_print")
STATUS_PRINTED = config.getint("statuses", "printed")

# --- Статусы обработки файла ---
PROC_NEW = config.getint("proc_status", "new")
PROC_DONE = config.getint("proc_status", "done")
PROC_ERROR = config.getint("proc_status", "error")
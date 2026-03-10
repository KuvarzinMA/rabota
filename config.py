# --- Параметры базы данных ---
DB_CONFIG = {
    "host": "10.2.1.50",
    "database": "rpismo",
    "user": "rpismo",
    "password": "22rpismo11"
}

# --- Параметры S3 (MinIO) ---
S3_CONFIG = {
    "endpoint_url": "http://10.2.1.50:9000",
    "aws_access_key_id": "minioadmin",
    "aws_secret_access_key": "minioadmin",
}
S3_BUCKET = "test-bucket"  # Убедись, что бакет в MinIO называется именно так

# --- Пути и секреты ---
MODEL_PATH = "postal_model.h5"
QR_SECRET = "secret"

# --- ID Типов писем (из таблицы letter_type) ---
TYPE_INIT = 1      # "init" - Инициативное письмо
TYPE_ANSWER = 2    # "answer" - Предоплаченный ответ
TYPE_FORWARD = 3   # "forward" - Письмо от родственника

# --- ID Статусов (из таблицы l_status) ---
STATUS_CLEAN = 1      # "clean"
STATUS_WRITED = 2     # "writed" (Написан, не прочитан)
STATUS_READED = 3     # "readed"
STATUS_FOR_PRINT = 4  # "for_print"
STATUS_PRINTED = 5    # "printed"

# --- Статусы обработки файла (таблица proc_files) ---
PROC_NEW = 0
PROC_DONE = 1
PROC_ERROR = -1
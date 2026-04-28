import os
from pathlib import Path


# ── Источник ──────────────────────────────────────────────────────────────────

FTP_ROOT = Path(os.getenv("FTP_ROOT", "C:/FTPStore"))

# Минимальный возраст файла перед переносом (rclone --min-age)
# Формат rclone: 10m, 1h, 2d …
MIN_FILE_AGE = os.getenv("MIN_FILE_AGE", "10s")

# Расширения, которые считаются сканами
SCAN_EXTENSIONS = {".pdf", ".tiff", ".tif", ".jpg", ".jpeg", ".png"}

# ── S3 / rclone ───────────────────────────────────────────────────────────────

# Имя remote из `rclone config`
S3_REMOTE = os.getenv("S3_REMOTE", "test")

# Префикс имени бакета — итого: mfu-printer-<printer_id>
S3_BUCKET_PREFIX = os.getenv("S3_BUCKET_PREFIX", "mfu-printer-")

# AWS-регион (нужен при создании бакетов)
AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")

# ── Параметры rclone ──────────────────────────────────────────────────────────

RCLONE_FLAGS: list[str] = [
    "--transfers",         os.getenv("RCLONE_TRANSFERS", "4"),
    "--checkers",          os.getenv("RCLONE_CHECKERS",  "8"),
    "--retries",           "3",
    "--low-level-retries", "10",
    "--stats",             "30s",
    "--log-level",         "INFO",
    "--inplace",           # Писать сразу в целевой ключ, без tmp-мусора
    # Бакет проверяется/создаётся в storage.py — не тратим HEAD на каждый вызов
    "--s3-no-check-bucket",
]

# Раскомментировать для тестового прогона без реальной записи
# RCLONE_FLAGS += ["--dry-run"]

# ── Включения файлов для rclone ───────────────────────────────────────────────

RCLONE_INCLUDE: list[str] = [
    arg
    for ext in SCAN_EXTENSIONS
    for arg in ("--include", f"*{ext}")
]

# ── PostgreSQL ────────────────────────────────────────────────────────────────

DB_CONFIG: dict = {
    "host":     os.getenv("DB_HOST",     ""),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME",     ""),
    "user":     os.getenv("DB_USER",     ""),
    "password": os.getenv("DB_PASSWORD", ""),
}

# Канал NOTIFY — воркер слушает именно его
DB_NOTIFY_CHANNEL = os.getenv("DB_NOTIFY_CHANNEL", "new_scan")

# Статус «только поступил, ещё не обработан»
PROC_NEW = 0

# ── Планировщик ───────────────────────────────────────────────────────────────

# Интервал между запусками в секундах (300 = 5 мин, 600 = 10 мин)
SCHEDULER_INTERVAL_SEC = int(os.getenv("SCHEDULER_INTERVAL", "300"))

import os
from pathlib import Path


# ── Источник ──────────────────────────────────────────────────────────────────

FTP_ROOT = Path(os.getenv("FTP_ROOT", "mnt/FTP"))

# Минимальный возраст файла перед переносом (rclone --min-age)
MIN_FILE_AGE = os.getenv("MIN_FILE_AGE", "10m")   # Формат rclone: 10m, 1h, 2d …

# Расширения, которые считаются сканами
SCAN_EXTENSIONS = {".pdf", ".tiff", ".tif", ".jpg", ".jpeg", ".png"}

# ── S3 / rclone ───────────────────────────────────────────────────────────────

# Имя remote из `rclone config`
S3_REMOTE = os.getenv("S3_REMOTE", "s3")

# Один общий бакет; регион и учреждение — папки внутри него
S3_BUCKET = os.getenv("S3_BUCKET", "mfu-scans")

# AWS-регион (нужен только при первом создании бакета)
AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")

# ── Параметры rclone ──────────────────────────────────────────────────────────

RCLONE_FLAGS: list[str] = [
    "--transfers", os.getenv("RCLONE_TRANSFERS", "4"),
    "--checkers",  os.getenv("RCLONE_CHECKERS",  "8"),
    "--retries",               "3",
    "--low-level-retries",     "10",
    "--stats",                 "30s",
    "--log-level",             "INFO",
    # Не проверять/создавать бакет при каждом вызове — мы управляем этим сами
    "--s3-no-check-bucket",
    # Писать файл сразу на место (атомарность в рамках одного файла)
    "--inplace",
]

# Раскомментировать для тестового прогона без реальной записи
# RCLONE_FLAGS += ["--dry-run"]

# ── Включения файлов для rclone ───────────────────────────────────────────────

RCLONE_INCLUDE: list[str] = [
    arg
    for ext in SCAN_EXTENSIONS
    for arg in ("--include", f"*{ext}")
]

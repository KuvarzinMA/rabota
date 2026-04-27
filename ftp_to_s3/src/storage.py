"""
Управление бакетом S3 через rclone.
Один бакет — структура внутри через папки: s3://mfu-scans/region/institution/
"""

import subprocess
from src.config import S3_REMOTE, S3_BUCKET, AWS_REGION
from src.logger import log


def ensure_bucket() -> bool:
    """
    Создаёт бакет S3, если он не существует.
    Вызывается один раз при старте — дальше используется --s3-no-check-bucket.
    """
    log.info(f"Проверяю бакет: s3://{S3_BUCKET}")

    check = subprocess.run(
        ["rclone", "lsd", f"{S3_REMOTE}:{S3_BUCKET}"],
        capture_output=True,
        text=True,
    )

    if check.returncode == 0:
        log.info(f"  Бакет существует: {S3_BUCKET}")
        return True

    log.info(f"  Создаю бакет: {S3_BUCKET} (регион: {AWS_REGION})")
    result = subprocess.run(
        [
            "rclone", "mkdir",
            f"{S3_REMOTE}:{S3_BUCKET}",
            "--s3-region", AWS_REGION,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        log.info(f"  Бакет создан: {S3_BUCKET}")
        return True

    log.error(f"  Не удалось создать бакет: {result.stderr.strip()}")
    return False

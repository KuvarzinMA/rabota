import subprocess
from src.config import S3_REMOTE, S3_BUCKET_PREFIX, AWS_REGION
from src.logger import log

# Кэш уже проверенных бакетов — не ходим в S3 лишний раз
_bucket_cache: set[str] = set()


def bucket_name(printer_id: str) -> str:
    """
    Формирует валидное имя бакета S3.
    Правила AWS: строчные буквы, цифры, дефисы; 3–63 символа.
    """
    raw = f"{S3_BUCKET_PREFIX}{printer_id}"
    name = "".join(c if c.isalnum() or c == "-" else "-" for c in raw.lower())
    while "--" in name:
        name = name.replace("--", "-")
    return name.strip("-")[:63]


def ensure_bucket(printer_id: str) -> bool:
    """
    Создаёт бакет для принтера, если он не существует.
    Результат кэшируется — повторный вызов не делает запросов в S3.
    """
    bname = bucket_name(printer_id)

    if bname in _bucket_cache:
        return True

    check = subprocess.run(
        ["rclone", "lsd", f"{S3_REMOTE}:{bname}"],
        capture_output=True, text=True,
    )

    if check.returncode == 0:
        log.debug(f"  Бакет существует: {bname}")
        _bucket_cache.add(bname)
        return True

    log.info(f"  🪣 Создаю бакет: {bname} (регион: {AWS_REGION})")
    result = subprocess.run(
        [
            "rclone", "mkdir",
            f"{S3_REMOTE}:{bname}",
            "--s3-region", AWS_REGION,
        ],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        log.info(f"  ✅ Бакет создан: {bname}")
        _bucket_cache.add(bname)
        return True

    log.error(f"  ❌ Не удалось создать бакет {bname}: {result.stderr.strip()}")
    return False

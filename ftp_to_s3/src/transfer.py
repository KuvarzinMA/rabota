"""
Перенос файлов одного принтера в его S3-бакет через rclone move.
Возвращает список перенесённых S3-ключей для регистрации в БД.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.config import S3_REMOTE, MIN_FILE_AGE, RCLONE_FLAGS, RCLONE_INCLUDE
from src.logger import log
from src.storage import bucket_name, ensure_bucket


@dataclass
class TransferResult:
    printer_id: str
    bucket: str
    success: bool
    moved_keys: list[str] = field(default_factory=list)  # имена файлов в бакете
    errors: list[str]     = field(default_factory=list)


def _parse_moved_keys(output: str) -> list[str]:
    """
    Извлекает имена перенесённых файлов из вывода rclone.

    rclone move --log-level INFO пишет строки вида:
        INFO  : scan001.pdf: Moved to s3:mfu-printer-42/scan001.pdf
    или (старые версии rclone):
        INFO  : scan001.pdf: Copied (new)
    """
    keys: list[str] = []

    # Паттерн 1: явный путь в S3 после «Moved to remote:bucket/»
    for match in re.finditer(r"Moved to [^:]+:[^/]+/(.+)", output):
        keys.append(match.group(1).strip())

    if keys:
        return keys

    # Паттерн 2: имя файла перед «: Copied» / «: Moved»
    for match in re.finditer(r"INFO\s+:\s+(.+?):\s+(?:Copied|Moved)", output):
        keys.append(match.group(1).strip())

    return keys


def move_printer(printer_dir: Path) -> TransferResult:
    """
    Переносит все готовые сканы принтера в его персональный бакет S3.

    Почему move:
        Файл удаляется с FTP только после подтверждения записи на стороне S3.

    Почему --min-age:
        rclone сам пропускает файлы моложе MIN_FILE_AGE — никакой ручной
        проверки mtime не нужно.
    """
    printer_id = printer_dir.name
    bname      = bucket_name(printer_id)

    result = TransferResult(
        printer_id=printer_id,
        bucket=bname,
        success=False,
    )

    if not ensure_bucket(printer_id):
        result.errors.append(f"Не удалось создать/проверить бакет {bname}")
        return result

    destination = f"{S3_REMOTE}:{bname}"

    cmd = [
        "rclone", "move",
        str(printer_dir),
        destination,
        "--min-age", MIN_FILE_AGE,
        *RCLONE_INCLUDE,
        *RCLONE_FLAGS,
    ]

    log.info(f"  ▶️  {printer_dir} → s3://{bname}/")
    log.debug(f"  CMD: {' '.join(cmd)}")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    combined = proc.stdout + "\n" + proc.stderr

    for line in proc.stdout.splitlines():
        log.info(f"    [rclone] {line}")

    for line in proc.stderr.splitlines():
        if any(kw in line for kw in ("ERROR", "CRITICAL", "Failed")):
            log.error(f"    [rclone] {line}")
            result.errors.append(line)
        else:
            log.debug(f"    [rclone] {line}")

    if proc.returncode == 0:
        result.success    = True
        result.moved_keys = _parse_moved_keys(combined)
        log.info(
            f"  ✅ {printer_id}: перенесено файлов: {len(result.moved_keys)}"
        )
    else:
        log.error(f"  ❌ rclone завершился с кодом {proc.returncode}: {printer_id}")

    return result

"""
Перенос файлов одного учреждения на S3 через rclone move.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.config import (
    S3_REMOTE, S3_BUCKET,
    MIN_FILE_AGE,
    RCLONE_FLAGS, RCLONE_INCLUDE,
)
from src.logger import log


@dataclass
class TransferResult:
    institution: str
    success: bool
    errors: list[str] = field(default_factory=list)


def _s3_destination(region: str, institution: str) -> str:
    """Формирует путь в S3: remote:bucket/region/institution"""
    return f"{S3_REMOTE}:{S3_BUCKET}/{region}/{institution}"


def move_institution(inst_dir: Path, region: str) -> TransferResult:
    """
    Запускает rclone move для одного учреждения.
    """
    institution = inst_dir.name
    destination = _s3_destination(region, institution)

    cmd = [
        "rclone", "move",
        str(inst_dir),
        destination,
        "--min-age", MIN_FILE_AGE,
        *RCLONE_INCLUDE,
        *RCLONE_FLAGS,
    ]

    log.info(f"  ▶ {inst_dir} → {destination}")
    log.debug(f"  CMD: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    errors: list[str] = []

    for line in result.stdout.splitlines():
        log.info(f"    [rclone] {line}")

    for line in result.stderr.splitlines():
        # rclone пишет INFO/DEBUG в stderr — отделяем настоящие ошибки
        if any(kw in line for kw in ("ERROR", "CRITICAL", "Failed")):
            log.error(f"    [rclone] {line}")
            errors.append(line)
        else:
            log.debug(f"    [rclone] {line}")

    success = result.returncode == 0
    if success:
        log.info(f" Готово: {institution}")
    else:
        log.error(f" Ошибка rclone (код {result.returncode}): {institution}")

    return TransferResult(institution=institution, success=success, errors=errors)

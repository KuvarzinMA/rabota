import subprocess
import sys
from dataclasses import dataclass, field

from src.config import FTP_ROOT, S3_BUCKET, S3_REMOTE, MIN_FILE_AGE
from src.logger import log
from src.scanner import iter_institutions
from src.storage import ensure_bucket
from src.transfer import move_institution, TransferResult


@dataclass
class RunStats:
    total: int = 0
    ok: int = 0
    failed: int = 0
    results: list[TransferResult] = field(default_factory=list)


def check_rclone() -> None:
    """Падаем сразу, если rclone не установлен."""
    if subprocess.run(["rclone", "version"], capture_output=True).returncode != 0:
        log.critical("rclone не найден. Установите: https://rclone.org/install/")
        sys.exit(1)


def run() -> RunStats:
    stats = RunStats()

    # Бакет создаётся/проверяется один раз
    if not ensure_bucket():
        log.critical("Не удалось подготовить бакет S3. Завершение.")
        sys.exit(1)

    for region, inst_dir in iter_institutions(FTP_ROOT):
        log.info(f"  Учреждение: {inst_dir.name}")
        stats.total += 1

        result = move_institution(inst_dir, region)
        stats.results.append(result)

        if result.success:
            stats.ok += 1
        else:
            stats.failed += 1

    return stats


def print_summary(stats: RunStats) -> None:
    log.info("=" * 60)
    log.info(" Итог:")
    log.info(f"   Учреждений обработано : {stats.total}")
    log.info(f"   Успешно               : {stats.ok}")
    log.info(f"   С ошибками            : {stats.failed}")

    if stats.failed:
        log.warning("Проблемные учреждения:")
        for r in stats.results:
            if not r.success:
                log.warning(f"   • {r.institution}")
                for err in r.errors:
                    log.warning(f"     {err}")

    log.info("=" * 60)


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("FTP → S3  (rclone move)")
    log.info(f"Источник       : {FTP_ROOT.resolve()}")
    log.info(f"Назначение     : s3://{S3_BUCKET}/  (remote: {S3_REMOTE})")
    log.info(f"Мин. возраст   : {MIN_FILE_AGE}  (--min-age)")
    log.info("=" * 60)

    check_rclone()
    stats = run()
    print_summary(stats)

    sys.exit(0 if stats.failed == 0 else 1)

"""
Точка входа.

Режимы запуска:
    python main.py              — один прогон
    python main.py --daemon     — бесконечный цикл каждые SCHEDULER_INTERVAL сек
"""

import subprocess
import sys

from src.config import FTP_ROOT, S3_BUCKET_PREFIX, S3_REMOTE, MIN_FILE_AGE
from src.logger import log
from src.scanner import iter_printers
from src.transfer import move_printer, TransferResult
from src.db import ensure_table, register_files


def run() -> list[TransferResult]:
    results: list[TransferResult] = []

    for printer_dir in iter_printers(FTP_ROOT):
        result = move_printer(printer_dir)
        results.append(result)

        if result.success and result.moved_keys:
            register_files(result.moved_keys, result.bucket)

    return results


def print_summary(results: list[TransferResult]) -> None:
    ok          = sum(1 for r in results if r.success)
    failed      = sum(1 for r in results if not r.success)
    total_files = sum(len(r.moved_keys) for r in results)

    log.info("=" * 60)
    log.info("📊 Итог:")
    log.info(f"   Принтеров обработано  : {len(results)}")
    log.info(f"   Успешно               : {ok}")
    log.info(f"   С ошибками            : {failed}")
    log.info(f"   Файлов перенесено     : {total_files}")

    if failed:
        log.warning("Проблемные принтеры:")
        for r in results:
            if not r.success:
                log.warning(f"   • {r.printer_id} → {r.bucket}")
                for err in r.errors:
                    log.warning(f"     {err}")

    log.info("=" * 60)


def bootstrap() -> None:
    if subprocess.run(["rclone", "version"], capture_output=True).returncode != 0:
        log.critical("rclone не найден. Установите: https://rclone.org/install/")
        sys.exit(1)
    ensure_table()


if __name__ == "__main__":
    daemon_mode = "--daemon" in sys.argv

    log.info("=" * 60)
    log.info("FTP → S3  (rclone move + PostgreSQL NOTIFY)")
    log.info(f"Источник       : {FTP_ROOT.resolve()}")
    log.info(f"Бакеты         : {S3_BUCKET_PREFIX}<printer_id>  (remote: {S3_REMOTE})")
    log.info(f"Мин. возраст   : {MIN_FILE_AGE}  (--min-age)")
    log.info(f"Режим          : {'демон' if daemon_mode else 'один прогон'}")
    log.info("=" * 60)

    bootstrap()

    if daemon_mode:
        from src.scheduler import run_loop

        def _job():
            print_summary(run())

        run_loop(_job)
    else:
        results = run()
        print_summary(results)
        sys.exit(0 if all(r.success for r in results) else 1)

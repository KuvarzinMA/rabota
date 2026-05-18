import signal
import time

from src.config import SCHEDULER_INTERVAL_SEC
from src.logger import log

_stop = False


def _handle_signal(sig, _frame):
    global _stop
    log.info(f"Получен сигнал {signal.Signals(sig).name}, завершаем после текущего прогона…")
    _stop = True


def run_loop(job_fn) -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    log.info(
        f"Планировщик запущен. "
        f"Интервал: {SCHEDULER_INTERVAL_SEC} сек "
        f"({SCHEDULER_INTERVAL_SEC // 60} мин). "
        f"Остановка: SIGTERM или Ctrl-C."
    )

    while not _stop:
        start = time.monotonic()
        log.info("=" * 60)
        log.info("▶ Запуск прогона")

        try:
            job_fn()
        except Exception as exc:
            # Не даём упасть планировщику из-за одиночной ошибки
            log.exception(f"Неожиданная ошибка в прогоне: {exc}")

        elapsed = time.monotonic() - start
        sleep_for = max(0, SCHEDULER_INTERVAL_SEC - elapsed)

        log.info(
            f"Прогон завершён за {elapsed:.1f}с. "
            f"Следующий через {sleep_for:.0f}с."
        )

        # Спим короткими кусками, чтобы быстро реагировать на сигнал
        _interruptible_sleep(sleep_for)

    log.info("Планировщик остановлен.")


def _interruptible_sleep(seconds: float, chunk: float = 1.0) -> None:
    remaining = seconds
    while remaining > 0 and not _stop:
        time.sleep(min(chunk, remaining))
        remaining -= chunk

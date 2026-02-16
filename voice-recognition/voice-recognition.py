import numpy as np
import librosa
import sys
from faster_whisper import WhisperModel
import time
start_time = time.time()
# --- КОНФИГУРАЦИЯ ---
FILE_PATH = "2.mp3"  # Имя твоего файла
STOP_WORD = "Ааоывал"  # Секретное слово
MODEL_SIZE = "small"  # Модель (tiny, base или путь к папке)
COMPUTE_TYPE = "int8"  # Оптимизация для CPU
SR = 16000  # Частота для Whisper
CHUNK_DURATION = 5  # Длительность сегмента анализа (сек)
MUSIC_THRESHOLD = 3500  # Порог детекции музыки

# --- ИНИЦИАЛИЗАЦИЯ ---
print(f"Загрузка модели Whisper...")
model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE, cpu_threads=12)


def is_music(audio_segment):
    """Анализ сегмента на наличие музыки."""
    centroid = librosa.feature.spectral_centroid(y=audio_segment, sr=SR)[0]
    return np.mean(centroid) > MUSIC_THRESHOLD


def process_file():
    print(f"Загрузка файла: {FILE_PATH}...")

    try:
        # Загружаем аудио целиком (или можно стримить, если файл огромный)
        audio, _ = librosa.load(FILE_PATH, sr=SR)
        total_duration = librosa.get_duration(y=audio, sr=SR)
        print(f"Длительность: {total_duration:.2f} сек.")

        # Разбиваем на сегменты
        samples_per_chunk = CHUNK_DURATION * SR

        for start_sample in range(0, len(audio), samples_per_chunk):
            end_sample = start_sample + samples_per_chunk
            chunk = audio[start_sample:end_sample]

            # Текущее время в секундах для логов
            current_time = start_sample / SR

            # 1. Проверка на музыку
            if is_music(chunk):
                print(f"[{current_time:.1f}с] ⚠️ ОБНАРУЖЕНА МУЗЫКА. Прекращаю обработку.")
                break

            # 2. Распознавание речи
            segments, _ = model.transcribe(chunk, language="ru", beam_size=5)

            for segment in segments:
                text = segment.text.lower().strip()
                if text:
                    print(f"[{current_time:.1f}с] {text}")

                    # 3. Проверка на стоп-слово
                    if STOP_WORD in text:
                        print(f"!!! СТОП-СЛОВО '{STOP_WORD}' НАЙДЕНО на {current_time:.1f} сек. !!!")
                        return

        print("--- Обработка файла завершена ---")

    except FileNotFoundError:
        print(f"Ошибка: Файл '{FILE_PATH}' не найден. Положи его в папку со скриптом.")
    except Exception as e:
        print(f"Произошла ошибка: {e}")


if __name__ == "__main__":
    process_file()

end_time = time.time()  # конец таймера
elapsed = end_time - start_time
print(f"Время выполнения: {elapsed:.2f} секунд")
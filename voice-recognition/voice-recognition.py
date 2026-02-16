import numpy as np
import librosa
from faster_whisper import WhisperModel
import time
from pydub import AudioSegment, effects

# --- КОНФИГУРАЦИЯ ---
FILE_PATH = "5.mp3"
STOP_WORD = "выфолвфыодлфывдлфоы"
MODEL_SIZE = "medium"  # Для CPU "small" — золотая середина
COMPUTE_TYPE = "int8"
SR = 16000


def preprocess_audio(file_path):
    """Выравнивание громкости собеседников перед распознаванием."""
    print("Предварительная обработка аудио (выравнивание громкости)...")
    audio = AudioSegment.from_file(file_path)

    # Нормализация и динамическое сжатие (делает тихое громким, громкое — тише)
    normalized_audio = effects.normalize(audio)
    # Применяем компрессор, чтобы вытянуть тихий голос
    compressed_audio = effects.compress_dynamic_range(normalized_audio)

    # Конвертируем в массив numpy для Whisper
    samples = np.array(compressed_audio.get_array_of_samples()).astype(np.float32) / 32768.0

    # Если стерео, усредняем в моно
    if compressed_audio.channels == 2:
        samples = samples.reshape((-1, 2)).mean(axis=1)

    return librosa.resample(samples, orig_sr=compressed_audio.frame_rate, target_sr=SR)


def process_file():
    start_time = time.time()

    print(f"Загрузка модели Whisper ({MODEL_SIZE})...")
    # Добавлено использование 4-8 потоков, обычно больше 12 замедляет процесс на CPU
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE, cpu_threads=8)

    try:
        audio_data = preprocess_audio(FILE_PATH)

        print("Начало распознавания...")
        # Мы не режем на куски вручную! Whisper сделает это сам умнее.
        segments, info = model.transcribe(
            audio_data,
            language="ru",
            beam_size=5,
            vad_filter=True,  # Убирает тишину и немузыкальные шумы автоматически
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        for segment in segments:
            text = segment.text.lower().strip()
            timestamp = f"[{segment.start:.1f}s -> {segment.end:.1f}s]"
            print(f"{timestamp} {text}")

            if STOP_WORD.lower() in text:
                print(f"\n!!! СТОП-СЛОВО '{STOP_WORD}' НАЙДЕНО !!!")
                break

        print(f"\n--- Готово! Время выполнения: {time.time() - start_time:.2f} сек ---")

    except Exception as e:
        print(f"Ошибка: {e}")


if __name__ == "__main__":
    process_file()
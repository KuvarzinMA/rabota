import os
import json
import subprocess
import time
import threading
from queue import Queue
from vosk import Model, KaldiRecognizer

# =========================
# КОНФИГУРАЦИЯ
# =========================
FILE_PATH = "5.mp3"
MODEL_PATH = r"C:\Users\Mishker\.cache\vosk\vosk-model-small-ru-0.22"
STOP_WORD = "барбоскины"
SAMPLE_RATE = 16000
CHUNK_SIZE = 32000

# =========================
# ИНИЦИАЛИЗАЦИЯ
# =========================
if not os.path.exists(MODEL_PATH):
    raise RuntimeError("Модель не найдена. Проверь MODEL_PATH")

print("Загрузка модели Vosk...")
model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)
recognizer.SetWords(True)

# =========================
# ФУНКЦИИ
# =========================
def read_audio(ffmpeg_cmd, queue):
    """Чтение аудио из ffmpeg в очередь"""
    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE)
    while True:
        data = process.stdout.read(CHUNK_SIZE)
        if not data:
            break
        queue.put(data)
    process.stdout.close()
    process.wait()
    queue.put(None)  # сигнал конца

def transcribe_parallel(file_path):
    """Потоковое распознавание через ffmpeg с параллельной обработкой"""
    ffmpeg_command = [
        "ffmpeg",
        "-loglevel", "quiet",
        "-i", file_path,
        "-af", "compand=0.3|0.3:6:-90/-60/-60/-40/-40/-15/-20/-10/-10/-5:6:0:-90:0.2,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-f", "s16le",
        "-"
    ]

    audio_queue = Queue(maxsize=10)
    threading.Thread(target=read_audio, args=(ffmpeg_command, audio_queue), daemon=True).start()

    full_text = []
    start_time = time.time()
    last_print = 0

    while True:
        data = audio_queue.get()
        if data is None:
            break

        if recognizer.AcceptWaveform(data):
            result = json.loads(recognizer.Result())
            text = result.get("text", "")
            if text:
                full_text.append(text)
                if STOP_WORD in text.lower():
                    print("!!! СТОП-СЛОВО ОБНАРУЖЕНО !!!")
                    return " ".join(full_text)
        else:
            partial = json.loads(recognizer.PartialResult())
            partial_text = partial.get("partial", "")
            if partial_text and time.time() - last_print > 0.5:
                print(f"[PARTIAL] {partial_text}")
                last_print = time.time()

    final_result = json.loads(recognizer.FinalResult())
    final_text = final_result.get("text", "")
    if final_text:
        full_text.append(final_text)

    elapsed = time.time() - start_time
    print(f"\nИтог: {' '.join(full_text)}")
    print(f"Время обработки: {elapsed:.2f} сек")

    return " ".join(full_text)

# =========================
# ЗАПУСК
# =========================
if __name__ == "__main__":
    try:
        transcribe_parallel(FILE_PATH)
    except Exception as e:
        print(f"Ошибка: {e}")

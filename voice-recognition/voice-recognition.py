import numpy as np
import librosa
from faster_whisper import WhisperModel
import time
from pydub import AudioSegment, effects
import re
from nltk.stem.snowball import SnowballStemmer

# ================== КОНФИГУРАЦИЯ ==================
FILE_PATH = "3.mp3"
MODEL_SIZE = "small"
COMPUTE_TYPE = "int8"
SR = 16000
MIN_HOLD_DURATION = 10

# Список слов в "основе"
KEYWORDS = {
    "войн",
    "террор",
    "теракт",
    "взрыв",
    "бомб",
    "убийств",
    "нападен"
}
# ==================================================

stemmer = SnowballStemmer("russian")


# ------------------ НОРМАЛИЗАЦИЯ ТЕКСТА ------------------

def detect_keywords(text):
    words = re.findall(r"\w+", text.lower())
    stems = [stemmer.stem(word) for word in words]

    found = set(stems).intersection(KEYWORDS)
    return found


# ------------------ АУДИО ПРЕПРОЦЕССИНГ ------------------

def preprocess_audio(file_path):
    audio = AudioSegment.from_file(file_path)
    normalized_audio = effects.normalize(audio)
    compressed_audio = effects.compress_dynamic_range(normalized_audio)

    samples = np.array(compressed_audio.get_array_of_samples()).astype(np.float32)
    samples /= np.iinfo(compressed_audio.array_type).max

    if compressed_audio.channels == 2:
        samples = samples.reshape((-1, 2)).mean(axis=1)

    samples = librosa.resample(
        samples,
        orig_sr=compressed_audio.frame_rate,
        target_sr=SR
    )

    return samples


# ------------------ ДЕТЕКЦИЯ МУЗЫКИ ------------------

def is_silence(y, threshold=0.001):
    return np.mean(np.abs(y)) < threshold


def detect_music_features(y, sr):
    spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)
    zcr = librosa.feature.zero_crossing_rate(y)

    tempo_array, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(tempo_array[0]) if isinstance(tempo_array, np.ndarray) else float(tempo_array)

    return {
        "centroid": float(np.mean(spectral_centroids)),
        "zcr": float(np.mean(zcr)),
        "tempo": tempo
    }


def is_hold_music(y, sr):
    if is_silence(y):
        return False, None

    features = detect_music_features(y, sr)

    if (
        features["centroid"] > 1500 and
        features["zcr"] > 0.03 and
        60 < features["tempo"] < 180
    ):
        return True, features

    return False, features


# ------------------ ОСНОВНАЯ ЛОГИКА ------------------

def process_file():
    start_time = time.time()

    print(f"Загрузка модели Whisper ({MODEL_SIZE})...")
    model = WhisperModel(
        MODEL_SIZE,
        device="cpu",
        compute_type=COMPUTE_TYPE,
        cpu_threads=8
    )

    audio_data = preprocess_audio(FILE_PATH)

    print("Начало распознавания речи...")
    segments, info = model.transcribe(
        audio_data,
        language="ru",
        beam_size=5,
        vad_filter=True
    )

    speech_detected = False
    last_speech_end = 0

    for segment in segments:
        text = segment.text.strip()
        timestamp = f"[{segment.start:.1f}s -> {segment.end:.1f}s]"
        print(f"{timestamp} {text}")

        if text:
            speech_detected = True
            last_speech_end = segment.end

            # 🔥 Проверка ключевых слов
            found_keywords = detect_keywords(text)
            if found_keywords:
                print(f"⚠ ОБНАРУЖЕНЫ ОПАСНЫЕ СЛОВА: {', '.join(found_keywords)}")

    total_duration = len(audio_data) / SR
    silence_after_speech = total_duration - last_speech_end

    print("\n--- Анализ удержания ---")

    if not speech_detected or silence_after_speech > MIN_HOLD_DURATION:
        music_detected, features = is_hold_music(audio_data, SR)

        if music_detected:
            print("\n🎵 ОБНАРУЖЕНА МУЗЫКА УДЕРЖАНИЯ")
            print(f"BPM: {features['tempo']:.1f}")
        else:
            print("Музыка не обнаружена.")
    else:
        print("Речь продолжается.")

    print(f"\nГотово! Время выполнения: {time.time() - start_time:.2f} сек")


if __name__ == "__main__":
    process_file()

import hashlib
import fitz
import cv2
import numpy as np


PDF_PATH = "../scan_20260212104232.pdf"

secret = "secret"

# зона интереса (левый верхний угол)ф
ZONE_X = 0.3
ZONE_Y = 0.3

# быстрый и полный зумы
FAST_ZOOM = 2.0
FULL_ZOOM = 3.5

# параметры адаптивной бинаризации
THRESH_BLOCK = 31
THRESH_C = 5


def pixmap_to_bgr(pix):
    """Конвертирует fitz.Pixmap в BGR-изображение OpenCV."""
    if pix.n not in (3, 4):
        raise ValueError(f"Unsupported pix format: {pix.n}")
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


def enhance(img):
    """Усиливает изображение для детекции QR-кодов."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        THRESH_BLOCK, THRESH_C
    )


def detect_qr(img, detector):
    """Пытается распознать QR-коды, обычный и усиленный метод."""
    ok, infos, points, _ = detector.detectAndDecodeMulti(img)
    if ok:
        return infos, points

    # усиленная обработка
    enhanced = enhance(img)
    ok, infos, points, _ = detector.detectAndDecodeMulti(enhanced)
    if ok:
        return infos, points

    return [], []


def process_detected_qr(infos, points, w, h, page_index):
    """Обрабатывает найденные QR и возвращает True, если что-то найдено в зоне интереса."""
    found = False
    for data, bbox in zip(infos, points):
        if not data:
            continue
        x = min(p[0] for p in bbox)
        y = min(p[1] for p in bbox)
        #Определение в каком месте qr-code-opencv
        if x < w * ZONE_X and y < h * ZONE_Y:
            print(f"Страница {page_index}: {data}")

            #Проверка на правильность контрольной суммы
            if verify_md5_checksum(data, secret):
                print("Контрольная сумма верна")
            else:
                print("Контрольная сумма НЕ совпадает")

            found = True
    return found


def generate_md5_checksum(txt: str, secret: str) -> str:
    """Создаёт MD5 контрольную сумму для текста с секретом."""
    combined = txt + secret
    return hashlib.md5(combined.encode('utf-8')).hexdigest()


def verify_md5_checksum(full_text: str, secret: str, sep: str = "-") -> bool:
    """
    Проверяет контрольную сумму в строке вида 'data-<checksum>'.
    full_text: строка с данными и контрольной суммой
    secret: секрет для генерации хеша
    sep: разделитель между данными и хешем
    """
    parts = full_text.rsplit(sep, 1)
    if len(parts) != 2:
        return False  # нет контрольной суммы
    txt, given_checksum = parts
    calc_checksum = generate_md5_checksum(txt, secret)
    return calc_checksum == given_checksum


try:
    doc = fitz.open(PDF_PATH)
except Exception as e:
    print(f"Ошибка при открытии PDF: {e}")
    exit(1)

detector = cv2.QRCodeDetector()

# список проходов: (zoom, высота клипа в процентах)
passes = [
    (FAST_ZOOM, 0.45),
    (FULL_ZOOM, 1.0)
]

for page_index, page in enumerate(doc, start=1):
    found = False

    for zoom, clip_ratio in passes:
        mat = fitz.Matrix(zoom, zoom)
        clip = None
        if clip_ratio < 1.0:
            clip = fitz.Rect(0, 0, page.rect.width * clip_ratio, page.rect.height * clip_ratio)

        pix = page.get_pixmap(matrix=mat, clip=clip)
        img = pixmap_to_bgr(pix)
        h, w = img.shape[:2]

        infos, points = detect_qr(img, detector)
        if process_detected_qr(infos, points, w, h, page_index):
            found = True

        # очистка памяти
        pix = None
        del img

        if found:
            break


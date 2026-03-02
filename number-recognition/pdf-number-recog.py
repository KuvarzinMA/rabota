import cv2
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import os
import fitz


def cv2_imshow(image, title="Debug"):
    plt.figure(figsize=(4, 2))
    plt.imshow(image, cmap='gray')
    plt.title(title)
    plt.axis('off')
    plt.show()


def run_recognition(pdf_path, model_path='postal_model.h5'):
    if not os.path.exists(model_path):
        print("Модель не найдена!")
        return
    model = tf.keras.models.load_model(model_path)

    # 1. Загрузка PDF с высоким качеством (важно для тонких линий)
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # 2. Обрезаем область индекса
    h_orig, w_orig = img.shape[:2]

    #ОБРЕЗКА, ТУТ МЕНЯТЬ ГДЕ НАХОДИТЬСЯ НОМЕР
    img_cropped = img[0:int(h_orig * 0.25), 0:int(w_orig * 0.6)]
    gray = cv2.cvtColor(img_cropped, cv2.COLOR_BGR2GRAY)

    # 3. Мощная предобработка для создания "маски-каркаса"
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Склеиваем цифры, чтобы найти их контуры
    kernel_dilate = np.ones((3, 3), np.uint8)
    process_img = cv2.dilate(thresh, kernel_dilate, iterations=1)

    cv2_imshow(process_img, "Общая бинаризация (склеенная)")

    # 4. Поиск и фильтрация контуров
    contours, _ = cv2.findContours(process_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if 50 < h < 300 and 15 < w < 200:  # Фильтр по размеру
            rects.append((x, y, w, h))

    rects = sorted(rects, key=lambda r: r[0])  # Слева направо

    # 5. Подготовка и распознавание
    full_index = ""
    # Берем первые 11 подходящих блоков
    for i, (x, y, w, h) in enumerate(rects[:11]):

        # ВЫРЕЗАЕМ С ЗАПАСОМ: берем чуть больше, чем нашел контур
        margin = 5
        roi = process_img[max(0, y - margin):y + h + margin, max(0, x - margin):x + w + margin]

        if roi.size == 0: continue

        # УСИЛЕНИЕ ДЛЯ НЕЙРОСЕТИ: делаем линии жирнее ПЕРЕД ресайзом
        # Это не даст цифре "исчезнуть"
        roi = cv2.dilate(roi, np.ones((2, 2), np.uint8), iterations=1)

        # ФИНАЛЬНАЯ ПОДГОТОВКА 32x32
        # Создаем черный холст
        final_roi = np.zeros((32, 32), dtype="uint8")

        # Рассчитываем масштаб, чтобы вписать цифру в 24x24 (оставляя поля)
        h_roi, w_roi = roi.shape[:2]
        scale = 24.0 / max(h_roi, w_roi)
        new_w, new_h = int(w_roi * scale), int(h_roi * scale)

        if new_w > 0 and new_h > 0:
            roi_res = cv2.resize(roi, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # Вставляем в центр 32x32
            start_y = (32 - new_h) // 2
            start_x = (32 - new_w) // 2
            final_roi[start_y:start_y + new_h, start_x:start_x + new_w] = roi_res

        # ВЫВОД КАЖДОЙ ЦИФРЫ (теперь они должны быть четкими и крупными)
        cv2_imshow(final_roi, f"ROI {i + 1} для нейросети")

        # Инференс
        roi_input = final_roi.astype("float32") / 255.0
        roi_input = np.expand_dims(np.expand_dims(roi_input, axis=-1), axis=0)

        pred = model.predict(roi_input, verbose=0)
        digit = np.argmax(pred)
        full_index += str(digit)

    print(f"\nРАСПОЗНАННЫЙ ТЕКСТ: {full_index}")


if __name__ == "__main__":
    run_recognition('scan.pdf')
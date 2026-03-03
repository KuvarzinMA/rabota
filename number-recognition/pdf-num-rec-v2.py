import cv2
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import os
import fitz


def cv2_imshow(image, title="Step"):
    plt.figure(figsize=(10, 5))
    plt.imshow(image, cmap='gray' if len(image.shape) == 2 else None)
    plt.title(title)
    plt.axis('off')
    plt.show()


def get_skew_angle(gray_img):
    """Определяет угол наклона по длинным горизонтальным структурам"""
    edges = cv2.Canny(gray_img, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 200, minLineLength=150, maxLineGap=20)
    angles = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if -15 < angle < 15: angles.append(angle)
    return np.median(angles) if angles else 0


def run_recognition(pdf_path, model_path='postal_model.h5'):
    if not os.path.exists(model_path):
        print("Ошибка: Модель не найдена!")
        return
    model = tf.keras.models.load_model(model_path)

    # 1. Загрузка и выравнивание всего листа
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    angle = get_skew_angle(gray_full)
    (h_f, w_f) = gray_full.shape
    M = cv2.getRotationMatrix2D((w_f // 2, h_f // 2), angle, 1.0)
    gray_full = cv2.warpAffine(gray_full, M, (w_f, h_f), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # 2. Обрезка ROI (твои коэффициенты)
    roi_h_limit = int(h_f * 0.15)
    roi_w_limit = int(w_f * 0.55)
    roi_gray = gray_full[0:roi_h_limit, 0:roi_w_limit]

    # 3. Бинаризация
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(roi_gray)
    thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 21, 10)

    # 4. ФИЛЬТРАЦИЯ "АНТИ-ТЕКСТ"
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        aspect_ratio = w / float(h)
        area = cv2.contourArea(cnt)

        # Удаляем маркеры (слишком широкие)
        if w > 150 and y < (roi_h_limit * 0.3):
            cv2.drawContours(thresh, [cnt], -1, 0, -1)

        # Удаляем сетку и мелкий текст (слишком маленькие или тонкие)
        if area < 50 or h < 30:
            cv2.drawContours(thresh, [cnt], -1, 0, -1)

        # Удаляем буквы (у букв обычно другое соотношение сторон, цифры индекса вытянуты)
        # Если объект слишком широкий для одной цифры (кроме '0' или '8'), это текст
        if aspect_ratio > 1.2 and y > (roi_h_limit * 0.5):
            cv2.drawContours(thresh, [cnt], -1, 0, -1)

    process_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
    cv2_imshow(process_img, "Только цифры (текст отфильтрован)")

    # 5. Нарезка
    final_contours, _ = cv2.findContours(process_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Ищем только объекты в "коридоре" индекса
    rects = []
    for c in final_contours:
        x, y, w, h = cv2.boundingRect(c)
        # Коридор индекса обычно находится между 30% и 90% высоты нашего ROI
        if 40 < h < 180 and (roi_h_limit * 0.25 < y < roi_h_limit * 0.95):
            rects.append((x, y, w, h))

    rects = sorted(rects, key=lambda r: r[0])

    extracted_rois = []
    full_index = ""
    for (x, y, w, h) in rects[:11]:
        p = 8
        roi = process_img[max(0, y - p):min(roi_gray.shape[0], y + h + p),
              max(0, x - p):min(roi_gray.shape[1], x + w + p)]
        if roi.size == 0: continue

        final_roi = np.zeros((32, 32), dtype="uint8")
        scale = 22.0 / max(roi.shape)
        nw, nh = int(roi.shape[1] * scale), int(roi.shape[0] * scale)
        roi_res = cv2.resize(roi, (nw, nh))
        final_roi[(32 - nh) // 2:(32 - nh) // 2 + nh, (32 - nw) // 2:(32 - nw) // 2 + nw] = roi_res
        extracted_rois.append(final_roi)

        roi_input = final_roi.astype("float32") / 255.0
        roi_input = np.expand_dims(np.expand_dims(roi_input, axis=-1), axis=0)
        full_index += str(np.argmax(model.predict(roi_input, verbose=0)))

    if extracted_rois:
        cv2_imshow(np.hstack(extracted_rois), f"Вход нейросети. Итог: {full_index}")
    print(f"РАСПОЗНАННЫЙ НОМЕР: {full_index}")


if __name__ == "__main__":
    run_recognition('scan.pdf')
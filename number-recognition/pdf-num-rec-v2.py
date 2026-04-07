import cv2
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import os
import fitz


def cv2_imshow(image, title="Step"):
    """Отображение этапов обработки"""
    plt.figure(figsize=(10, 5))
    plt.imshow(image, cmap='gray' if len(image.shape) == 2 else None)
    plt.title(title)
    plt.axis('off')
    plt.show()


def get_skew_angle(gray_img):
    """Определяет угол наклона листа"""
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
        print("Ошибка: Файл модели .h5 не найден!")
        return

    model = tf.keras.models.load_model(model_path)

    # --- 1. ЗАГРУЗКА И ВЫРАВНИВАНИЕ ---
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

    # --- 2. ОБРЕЗКА ROI (ВАШИ НОВЫЕ КОЭФФИЦИЕНТЫ) ---
    y_start = int(h_f * 0.05)
    y_end = int(h_f * 0.35)
    x_start = int(w_f * 0)
    x_end = int(w_f * 0.55)

    roi_gray = gray_full[y_start:y_end, x_start:x_end].copy()
    roi_h, roi_w = roi_gray.shape

    # --- 3. УДАЛЕНИЕ QR-КОДА (ДО БИНАРИЗАЦИИ) ---
    qr_detector = cv2.QRCodeDetector()
    retval, points, _ = qr_detector.detectAndDecode(roi_gray)

    if points is not None:
        cv2.fillPoly(roi_gray, points.astype(int), 255)
    else:
        # Резервный поиск QR по плотности (если детектор не сработал)
        grad = cv2.morphologyEx(roi_gray, cv2.MORPH_GRADIENT, np.ones((5, 5), np.uint8))
        _, qr_mask = cv2.threshold(grad, 60, 255, cv2.THRESH_BINARY)
        closed = cv2.morphologyEx(qr_mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
        cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if cv2.contourArea(c) > 4000:
                cv2.drawContours(roi_gray, [c], -1, 255, -1)

    # --- 4. БИНАРИЗАЦИЯ И ФИЛЬТРАЦИЯ ---
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(roi_gray)
    thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 21, 10)

    # Очистка маски от мусора
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > 150 or cv2.contourArea(cnt) < 50 or h < 30:
            cv2.drawContours(thresh, [cnt], -1, 0, -1)

    # Жирнение для лучшего поиска контуров
    process_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
    cv2_imshow(process_img, "Итоговая маска (ориентир)")

    # --- 5. НАРЕЗКА И НЕЙРОСЕТЬ ---
    final_contours, _ = cv2.findContours(process_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for c in final_contours:
        x, y, w, h = cv2.boundingRect(c)
        # Поиск "коридора" индекса
        if 40 < h < 180 and (roi_h * 0.2 < y < roi_h * 0.95):
            rects.append((x, y, w, h))

    rects = sorted(rects, key=lambda r: r[0])

    extracted_rois = []
    full_index = ""

    for (x, y, w, h) in rects:
        p = 5  # Небольшой отступ
        y1, y2 = max(0, y - p), min(roi_h, y + h + p)
        x1, x2 = max(0, x - p), min(roi_w, x + w + p)

        digit_roi = process_img[y1:y2, x1:x2]
        if digit_roi.size == 0: continue

        # --- ИСПРАВЛЕННАЯ ПОДГОТОВКА ЦИФРЫ ---
        final_roi = np.zeros((32, 32), dtype="uint8")

        # Масштабируем, используя метод "ближайшего соседа", чтобы не терять пиксели
        scale = 24.0 / max(digit_roi.shape)
        nw, nh = int(digit_roi.shape[1] * scale), int(digit_roi.shape[0] * scale)
        roi_res = cv2.resize(digit_roi, (nw, nh), interpolation=cv2.INTER_NEAREST)

        # Слегка "жирним" результат ресайза, чтобы линии были плотными
        roi_res = cv2.dilate(roi_res, np.ones((2, 2), np.uint8), iterations=1)

        dy, dx = (32 - nh) // 2, (32 - nw) // 2
        final_roi[dy:dy + nh, dx:dx + nw] = roi_res
        extracted_rois.append(final_roi)

        # Предсказание
        roi_input = final_roi.astype("float32") / 255.0
        roi_input = np.expand_dims(np.expand_dims(roi_input, axis=-1), axis=0)
        prediction = model.predict(roi_input, verbose=0)
        full_index += str(np.argmax(prediction))

    # Финальный вывод нарезанных цифр (как они пошли в нейросеть)
    if extracted_rois:
        cv2_imshow(np.hstack(extracted_rois), f"Вход нейросети. Результат: {full_index}")

    print(f"РАСПОЗНАННЫЙ НОМЕР: {full_index}")


if __name__ == "__main__":
    run_recognition('scan_20260406152358.pdf')